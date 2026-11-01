"""解说文本动作分类器训练（实验 4 本侧）。

语料：实验 1 清洗后的直播吧解说 40,376 条（data/processed/texts/livetext/）。
标签：关键词规则弱监督（无人工标注），按篮球动作事件分 10 类；
      该分类器同时服务实验 4 文本分类页/图文匹配页，并为实验 5"事件→解说"配对铺路。
模型：char TF-IDF(1-3 gram) + LinearSVC（轻量、CPU 毫秒级、免深度依赖）。
产出：app/ml/text_action_clf.joblib（pipeline）+ text_clf_meta.json（指标与规则）。

用法（在 exp4/backend 下）：
    python train_text_clf.py --data ../../data/processed/texts/livetext/commentary.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import classification_report, f1_score, accuracy_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC

# ---- 弱标签规则（顺序即优先级：先具体事件，后泛化描述）----
RULES: list[tuple[str, str]] = [
    ("罚球", r"罚球|罚篮|两罚|罚中|罚丢|加罚|技术犯规罚"),
    ("犯规违例", r"犯规|违例|走步|二次运球|翻腕|吹罚|哨响|罚出|夺权|挑战|裁判"),
    ("暂停换人", r"暂停|换人|下场|替补|登场|轮换|首发|回到场上|挑战成功"),
    ("抢断", r"抢断|断球|切球|抢下球权"),
    ("盖帽", r"盖帽|封盖|大帽|扇出"),
    ("篮板", r"篮板|前场板|后场板|争抢篮板"),
    ("助攻传球", r"助攻|传球|传给|妙传|分球|击地|长传|手递手|送出"),
    ("投篮", r"投篮|出手|跳投|三分|3分|两分|2分|上篮|扣篮|抛投|补篮|勾手|后仰|干拔|命中|得分|打进|球进|空心|打铁|不中|偏出|绝杀|压哨|抛投"),
    ("比分局势", r"比分|领先|落后|追分|反超|打停|分差|拉开|迫近|咬住|胶着|战成|打成|领先优势|稳住"),
    ("阵容战术", r"战术|挡拆|掩护|落位|站位|阵型|联防|盯人|包夹|夹击|协防|换防"),
]
OTHER = "其他"


def weak_label(text: str) -> str:
    for label, pat in RULES:
        if re.search(pat, text):
            return label
    return OTHER


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="../../data/processed/texts/livetext/commentary.jsonl")
    ap.add_argument("--out-dir", default="app/ml")
    ap.add_argument("--test-size", type=float, default=0.1)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    src = Path(args.data)
    texts, labels = [], []
    with src.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            t = json.loads(line).get("text", "").strip()
            if t:
                texts.append(t)
                labels.append(weak_label(t))
    y = np.array(labels)
    print(f"语料: {src} -> {len(texts)} 条")
    dist = {c: int((y == c).sum()) for c in sorted(set(y))}
    print("弱标签分布:", json.dumps(dist, ensure_ascii=False))

    pipe = Pipeline([
        ("tfidf", TfidfVectorizer(analyzer="char", ngram_range=(1, 3), min_df=3,
                                  max_features=50000, sublinear_tf=True)),
        ("clf", LinearSVC(C=1.0)),
    ])
    tr_x, te_x, tr_y, te_y = train_test_split(
        texts, y, test_size=args.test_size, random_state=args.seed, stratify=y)
    pipe.fit(tr_x, tr_y)
    pred = pipe.predict(te_x)
    acc = accuracy_score(te_y, pred)
    macro = f1_score(te_y, pred, average="macro")
    report = classification_report(te_y, pred, output_dict=True, zero_division=0)
    print(f"留出集({len(te_y)}条): accuracy={acc:.4f}  macro-F1={macro:.4f}")
    for c in sorted(report):
        if c in ("accuracy", "macro avg", "weighted avg"):
            continue
        print(f"  {c:<6} P={report[c]['precision']:.3f} R={report[c]['recall']:.3f} "
              f"F1={report[c]['f1-score']:.3f} n={int(report[c]['support'])}")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipe, out_dir / "text_action_clf.joblib")

    # 域外探测校准：短文本（"换人了"）决策值低，故域判定采用"规则命中 OR 概率阈值"
    import warnings
    warnings.filterwarnings("ignore")
    ood = ["今天天气晴朗适合出游", "股市今日大幅上涨", "这道菜的做法很简单",
           "新款手机明天发布", "明天的会议改到下午三点", "周末去爬山看风景", "这部电影评分很高"]
    def max_prob(p, t):
        d = p.decision_function([t])[0]
        e = np.exp(d - d.max())
        return float((e / e.sum()).max())
    ood_probs = [round(max_prob(pipe, t), 3) for t in ood]
    in_domain_probs = [round(max_prob(pipe, t), 3) for t in
                       ["詹姆斯三分出手命中！", "这球犯规了裁判没吹", "球进了！"]]
    thr = 0.5   # 域外最高 0.498，取 0.5；配合规则 OR（见 domain_mode）
    print(f"域外样本 max_prob: {ood_probs} | 域内: {in_domain_probs} | 概率阈值取 {thr}")

    meta = {
        "model": "char-tfidf(1-3)+LinearSVC",
        "corpus": str(src), "corpus_size": len(texts),
        "train_size": len(tr_x), "test_size": len(te_y),
        "accuracy": round(float(acc), 4), "macro_f1": round(float(macro), 4),
        "per_class": {c: {k: round(v, 4) for k, v in report[c].items() if k != "support"}
                      for c in report if c not in ("accuracy",)},
        "label_distribution": dist,
        "rules": [{"label": l, "pattern": p} for l, p in RULES],
        "domain_conf_thr": thr,
        "domain_mode": "prob>=thr 或 命中弱标签规则关键词（短文本决策值低，规则优先保召回）",
        "ood_max_probs": ood_probs, "in_domain_probs": in_domain_probs,
        "trained_at": datetime.now().isoformat(timespec="seconds"),
    }
    (out_dir / "text_clf_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已保存: {out_dir/'text_action_clf.joblib'} 与 text_clf_meta.json")


if __name__ == "__main__":
    main()

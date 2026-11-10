# -*- coding: utf-8 -*-
"""实验5 微调数据构建（总包 §2 / 微调线执行手册 §1）。

输入：backend/ml/split_train.jsonl（32,377 条）、split_test.jsonl（3,110 条）
输出：exp5/data/agent_finetune_data.json（100 条：60 分类 + 40 生成）
      exp5/data/agent_eval_10.json（10 道考题）
      exp5/data/build_notes.md（核对记录与统计）

标签体系与实验4 文本分类器完全一致（train_text_clf.py 的 10 类规则）：
罚球 / 犯规违例 / 暂停换人 / 抢断 / 盖帽 / 篮板 / 助攻传球 / 投篮 / 比分局势 / 阵容战术
"""
from __future__ import annotations

import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TRAIN = REPO / "exp4/complete_web_system/backend/ml/split_train.jsonl"
TEST = REPO / "exp4/complete_web_system/backend/ml/split_test.jsonl"
OUT_DIR = REPO / "exp5/data"

RULES: list[tuple[str, str]] = [
    ("罚球", r"罚球|罚篮|两罚|罚中|罚丢|加罚|技术犯规罚"),
    ("犯规违例", r"犯规|违例|走步|二次运球|翻腕|吹罚|哨响|罚出|夺权|挑战|裁判"),
    ("暂停换人", r"暂停|换人|下场|替补|登场|轮换|首发|回到场上|挑战成功"),
    ("抢断", r"抢断|断球|切球|抢下球权"),
    ("盖帽", r"盖帽|封盖|大帽|扇出"),
    ("篮板", r"篮板|前场板|后场板|争抢篮板"),
    ("助攻传球", r"助攻|传球|传给|妙传|分球|击地|长传|手递手|送出"),
    ("投篮", r"投篮|出手|跳投|三分|3分|两分|2分|上篮|扣篮|抛投|补篮|勾手|后仰|干拔|命中|得分|打进|球进|空心|打铁|不中|偏出|绝杀|压哨"),
    ("比分局势", r"比分|领先|落后|追分|反超|打停|分差|拉开|迫近|咬住|胶着|战成|打成|领先优势|稳住"),
    ("阵容战术", r"战术|挡拆|掩护|落位|站位|阵型|联防|盯人|包夹|夹击|协防|换防"),
]
LABELS = [label for label, _ in RULES]
OTHER = "其他"

# 生成题的局面细节（动作类型 → 场上细节）
def derive_detail(label: str, sentence: str) -> str:
    """从解说句本身反推"场上细节"，保证 事件描述 ↔ 解说句 语义一致。

    （手册要求 input 的事件类型与 output 解说句同类；若凭空指定细节，
      容易出现"事件=长传、解说=击地"这种同大类但不同动作的错配。）
    """
    if label == "助攻传球":
        if "击地" in sentence:
            return "击地传球"
        if "长传" in sentence:
            return "长传快攻"
        if "手递手" in sentence:
            return "手递手配合"
        return "转移球"
    if label == "暂停换人":
        return "换人调整" if re.search(r"换人|替补|登场|换上|首发", sentence) else "请求暂停"
    if label == "盖帽":
        return "追身封盖" if re.search(r"追防|追身", sentence) else "篮下大帽"
    if label == "篮板":
        if "前场板" in sentence:
            return "前场篮板"
        if re.search(r"后场板|防守篮板", sentence):
            return "后场篮板"
        return "篮板拼抢"
    if label == "投篮":
        if "三分" in sentence or "3分" in sentence:
            return "三分出手"
        if "上篮" in sentence or "挑篮" in sentence:
            return "突破上篮"
        if "扣" in sentence:
            return "快攻扣篮"
        if "跳投" in sentence or "后仰" in sentence:
            return "中距离急停跳投"
        return "出手投篮"
    if label == "犯规违例":
        if "走步" in sentence:
            return "走步违例"
        if "违例" in sentence:
            return "违例"
        if "and one" in sentence.lower():
            return "投篮犯规"
        return "进攻犯规" if "进攻犯规" in sentence else "防守犯规"
    if label == "抢断":
        return "边线断球" if re.search(r"边线|出界", sentence) else "中场抢断"
    if label == "罚球":
        if "加罚" in sentence:
            return "加罚"
        return "两罚" if "两罚" in sentence else "罚球"
    if label == "比分局势":
        if "反超" in sentence:
            return "比分反超"
        if "追平" in sentence or "扳平" in sentence:
            return "比分追平"
        if "打停" in sentence:
            return "打停对手"
        if "领先" in sentence:
            return "比分领先"
        if "落后" in sentence:
            return "比分落后"
        if "拉开" in sentence:
            return "分差被拉开"
        if re.search(r"差距|胶着|接近", sentence):
            return "比分胶着"
        return "比分变化"
    if label == "阵容战术":
        if "挡拆" in sentence:
            return "挡拆配合"
        if "掩护" in sentence:
            return "无球掩护"
        if "包夹" in sentence or "夹击" in sentence:
            return "包夹防守"
        if "联防" in sentence or "盯人" in sentence:
            return "联防盯人"
        return "换防"
    return label
CONTEXTS = [
    "第四节最后两分钟",
    "开局阶段",
    "第三节中段",
    "暂停回来后的第一次进攻",
    "比赛最后 10 秒",
    "第二节轮换时间",
]


def weak_label(text: str) -> str:
    for label, pat in RULES:
        if re.search(pat, text):
            return label
    return OTHER


NOISE = [
    re.compile(r"^\s*@"),                      # 用户评论
    re.compile(r"^\s*【GIF】"),                # 动图搬运
    re.compile(r"\d+\s*分\s*\d+\s*板"),        # 技术统计整行
    re.compile(r"^\s*【直播吧数据】"),
    re.compile(r"[\]]\s*[^\[\]]*\s*\["),       # 带比分标签的长行
    re.compile(r"^\s*[^\s：:]{1,8}[：:]"),      # "某某：……" 记者/网友发言
    re.compile(r"首发[：:]"),                   # 首发名单
    re.compile(r"加回来|扣掉1分|最终比分|判罚更改"),  # 赛后改分/判罚更正
    re.compile(r"不好意思|抱歉|说错了|打错了"),          # 口误更正
]

# 人工核对时发现的预标错误（关键词命中但动作不是它）
MANUAL_FIX = {
    "罚球线！顶开人！跳投得分！[马刺49-56太阳]": "投篮",
    "罚球线后仰的跳投压哨两分潇洒进！！！[鹈鹕51-53热火]": "投篮",
    # 段3 审计（audit_data.py 逐条复核）后修正：关键词命中但不是该动作
    "首发五人组！乌度卡弧顶指挥KD、申京、小贾、阿门、范乔丹跑战术": "阵容战术",
    "躲开封盖！！": "投篮",
    "接传球！起飞Slammmmmm Dunk！！[老鹰100-94步行者]": "投篮",
    "弧顶稳住！": "阵容战术",
    "拉开距离！": "阵容战术",
    "远端拉开！": "阵容战术",
    "分球被断！": "抢断",
    "拉开背身打！": "阵容战术",
    "拉开空间！！": "阵容战术",
    "拉开面筐突！": "阵容战术",
    "老鹰稳住！！找右侧底角弗莱明斯！！": "阵容战术",
}

# 审计中判定为无教学价值的样本（比赛计时/统计碎片），直接剔除
DROP = {
    "2分23！",
    "3分5！！",
}
FIXED_COUNT = 0


def is_noise(text: str) -> bool:
    if any(p.search(text) for p in NOISE):
        return True
    if len(text) < 5 or len(text) > 120:
        return True
    return False


def load_rows(path: Path) -> list[str]:
    texts: list[str] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            text = (json.loads(line).get("text") or "").strip()
            if not text:
                continue
            if len(text) > 500:  # 手册 §0：丢掉超长
                continue
            if is_noise(text) or text in DROP:
                continue
            texts.append(text)
    return texts


def label_of(text: str) -> str:
    global FIXED_COUNT
    if text in MANUAL_FIX:
        FIXED_COUNT += 1
        return MANUAL_FIX[text]
    # "罚球线" 是位置不是罚球：罚球线附近的跳投/上篮应归投篮
    if re.search(r"罚球线", text) and not re.search(r"两罚|罚篮|加罚|罚中|罚丢|罚球不进|第[一二三]罚", text):
        if re.search(r"跳投|出手|命中|得分|上篮|三分|两分|扣篮|后仰|打板|抛投|勾手|补篮", text):
            FIXED_COUNT += 1
            return "投篮"
    # "拉开" 单独出现多指拉开空间/单打，不是比分拉开
    if "拉开" in text and not re.search(r"分差|比分|领先|落后|\\d+\\s*分|优势", text):
        if weak_label(text) == "比分局势":
            FIXED_COUNT += 1
            return "阵容战术"
    return weak_label(text)


def dedupe(texts: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for t in texts:
        key = re.sub(r"[\s，。！？、,.!?~～…\-—]+", "", t)
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out


def sample_by_class(pool: dict[str, list[str]], per_class: int, rng: random.Random,
                    skip: set[str] | None = None) -> list[tuple[str, str]]:
    picked: list[tuple[str, str]] = []
    skip = skip or set()
    for label in LABELS:
        candidates = [t for t in pool.get(label, []) if t not in skip]
        rng.shuffle(candidates)
        # 长短搭配：先取 2 条短的、再补长的，避免全是同一节奏
        candidates.sort(key=len)
        chosen: list[str] = []
        if len(candidates) >= per_class:
            half = per_class // 2
            chosen = candidates[:half] + candidates[-(per_class - half):]
        else:
            chosen = candidates[:per_class]
        for t in chosen:
            picked.append((label, t))
    return picked


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rng = random.Random(42)

    train_raw = load_rows(TRAIN)
    test_raw = load_rows(TEST)
    train = dedupe(train_raw)
    test = dedupe(test_raw)

    pool: dict[str, list[str]] = {}
    for t in train:
        pool.setdefault(label_of(t), []).append(t)
    dist = {k: len(v) for k, v in sorted(pool.items(), key=lambda kv: -len(kv[1]))}

    # 60 条分类题：10 类 × 6 条（跳过"其他"）
    cls_pairs = sample_by_class(pool, 6, rng)
    used = {t for _, t in cls_pairs}

    # 40 条生成题：10 类 × 4 条，output 取同类真人原句
    gen_pairs: list[tuple[str, str]] = []
    for label in LABELS:
        picked = sample_by_class({label: pool.get(label, [])}, 4, rng, skip=used)
        for idx, (_, sentence) in enumerate(picked):
            clean = re.sub(r"\[[^\]]*\]\s*$", "", sentence).strip()
            gen_pairs.append((f"{derive_detail(label, clean or sentence)}；当前局面：{CONTEXTS[idx % len(CONTEXTS)]}",
                              clean or sentence))
            used.add(sentence)

    finetune = []
    for label, text in cls_pairs:
        finetune.append({
            "instruction": "判断下面这句篮球解说的动作类别，只输出类别名，不要解释。可选类别：罚球、犯规违例、暂停换人、抢断、盖帽、篮板、助攻传球、投篮、比分局势、阵容战术",
            "input": text,
            "output": label,
        })
    for situation, sentence in gen_pairs:
        finetune.append({
            "instruction": "你是篮球解说员。根据场上局面写一句中文解说，风格贴近真人直播解说：短句、有情绪、跟着动作走。",
            "input": f"事件：{situation}",
            "output": sentence,
        })

    # 10 道考题：test 卷取样，覆盖 10 类
    finetune_inputs = {item["input"] for item in finetune}
    test_pool: dict[str, list[str]] = {}
    for t in test:
        test_pool.setdefault(label_of(t), []).append(t)

    # 10 道考题：人工从 test 卷候选中逐条挑定并确认标签（手册 §1.3 要求人工确认）
    EXAM_VERIFIED = [
        ("罚球", "沃特森上罚球线！！"),
        ("犯规违例", "拿球又走步了！！"),
        ("暂停换人", "骑士换人了！！海佐尼亚上来了！！"),
        ("抢断", "贺思瑶断球！！"),
        ("盖帽", "布莱恩特协防大帽！！"),
        ("篮板", "埃纳鲁纳篮板！给快下海佐尼亚！！"),
        ("助攻传球", "分球贾明儒！！"),
        ("投篮", "托马斯左侧接球三分！"),
        ("比分局势", "第一节结束！山西领先11分！"),
        ("阵容战术", "借掩护加速突破！"),
    ]
    test_set = set(test)

    print("\n=== 考题候选（每类 4 条，人工挑选/确认）===")
    for label in LABELS:
        cands = [t for t in test_pool.get(label, []) if t not in finetune_inputs]
        rng.shuffle(cands)
        print(f"\n[{label}] 共 {len(test_pool.get(label, []))} 条")
        for t in cands[:4]:
            print(f"   - {t}")

    exam_pairs = EXAM_VERIFIED

    exam = [{"id": i + 1, "input": text, "output": label, "verified": True}
            for i, (label, text) in enumerate(exam_pairs)]
    missing = [t for _, t in EXAM_VERIFIED if t not in test_set]
    assert not missing, f"考题不在 test 卷里：{missing}"

    # 自检断言
    finetune_inputs = {item["input"] for item in finetune}
    exam_inputs = {item["input"] for item in exam}
    assert len(finetune) == 100, f"练习题数量 {len(finetune)} != 100"
    assert len(exam) == 10, f"考题数量 {len(exam)} != 10"
    assert len(finetune_inputs) == 100, "练习题内部有重复 input"
    leak = exam_inputs & finetune_inputs
    assert not leak, f"考题与练习题存在泄漏：{list(leak)[:3]}"
    labels_used = {x["output"] for x in finetune if "动作类别" in x["instruction"]}
    assert labels_used <= set(LABELS), f"出现体系外标签：{labels_used - set(LABELS)}"

    (OUT_DIR / "agent_finetune_data.json").write_text(
        json.dumps(finetune, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / "agent_eval_10.json").write_text(
        json.dumps(exam, ensure_ascii=False, indent=2), encoding="utf-8")

    stats = {
        "train_rows": len(train_raw), "train_unique": len(train),
        "test_rows": len(test_raw), "test_unique": len(test),
        "label_distribution": dist,
        "finetune_class": sum(1 for x in finetune if x["output"] in LABELS and "动作类别" in x["instruction"]),
        "finetune_gen": sum(1 for x in finetune if "解说员" in x["instruction"]),
        "exam": len(exam),
        "prelabel_corrected": sum(1 for label, t in cls_pairs if weak_label(t) != label),
    }
    (OUT_DIR / "build_stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(stats, ensure_ascii=False, indent=1))
    print("\n=== 60 条分类练习题（核对用）===")
    for item in finetune:
        if "动作类别" in item["instruction"]:
            print(f'[{item["output"]}] {item["input"]}')
    print("\n=== 10 道考题（待人工确认）===")
    for item in exam:
        print(f'{item["id"]:2d}. [{item["output"]}] {item["input"]}')
    return 0


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""段4 扩展评估（审计用）：10 道题太少，±1 题就是 10 个百分点。

从 split_test 再抽 100 条（排除考题 10 条），用同一 prompt 跑四个"考生"：
  joblib 分类器 / 本地基座 / 本地基座+LoRA / DeepSeek 零样本
产物：exp5/eval/extended_100.json
"""
from __future__ import annotations

import json
import random
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "exp4/complete_web_system/backend"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(Path(__file__).parent))

import httpx  # noqa: E402
import joblib  # noqa: E402
import torch  # noqa: E402
from openai import OpenAI  # noqa: E402
from peft import PeftModel  # noqa: E402
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig  # noqa: E402

from app.agent.providers import load_env  # noqa: E402
from prompt import LABELS, build_prompt, parse_label  # noqa: E402

TEST = BACKEND / "ml/split_test.jsonl"
EXAM = REPO / "exp5/data/agent_eval_10.json"
ADAPTER = REPO / "exp5/adapters/qwen3-1.7b-lora"
OUT = REPO / "exp5/eval/extended_100.json"


def rule_label(text: str) -> str:
    rules = [
        ("罚球", r"罚球|罚篮|两罚|罚中|罚丢|加罚"),
        ("犯规违例", r"犯规|违例|走步|二次运球|翻腕|吹罚|哨响|挑战|裁判"),
        ("暂停换人", r"暂停|换人|下场|替补|登场|轮换|首发"),
        ("抢断", r"抢断|断球|切球|抢下球权"),
        ("盖帽", r"盖帽|封盖|大帽|扇出"),
        ("篮板", r"篮板|前场板|后场板"),
        ("助攻传球", r"助攻|传球|传给|妙传|分球|击地|长传|手递手|送出"),
        ("投篮", r"投篮|出手|跳投|三分|上篮|扣篮|抛投|补篮|勾手|后仰|命中|得分|打进|球进|绝杀|压哨"),
        ("比分局势", r"比分|领先|落后|追分|反超|打停|分差|胶着|战成|打成"),
        ("阵容战术", r"战术|挡拆|掩护|落位|站位|阵型|联防|盯人|包夹|夹击|协防|换防"),
    ]
    for label, pat in rules:
        if re.search(pat, text):
            return label
    return "其他"


def build_sample(n_per_class=10, seed=7):
    exam_texts = {x["input"] for x in json.loads(EXAM.read_text(encoding="utf-8"))}
    pool = {}
    for line in TEST.open(encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        text = (json.loads(line).get("text") or "").strip()
        if not text or text in exam_texts or len(text) < 5 or len(text) > 120:
            continue
        if text.startswith("@") or "分" in text and re.search(r"\d+\s*分\s*\d+\s*板", text):
            continue
        label = rule_label(text)
        if label == "其他":
            continue
        pool.setdefault(label, []).append(text)
    rng = random.Random(seed)
    picked = []
    for label in LABELS:
        cands = pool.get(label, [])
        rng.shuffle(cands)
        picked += [(label, t) for t in cands[:n_per_class]]
    rng.shuffle(picked)
    return picked


def strip_think(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()


def local_generate(model, tok, text):
    prompt = tok.apply_chat_template(
        [{"role": "user", "content": build_prompt(text)}], tokenize=False, add_generation_prompt=True,
    ) + "<think>\n\n</think>\n\n"
    inputs = tok(prompt, return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=16, do_sample=False, pad_token_id=tok.eos_token_id)
    raw = tok.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
    return raw, parse_label(strip_think(raw))


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap_model = sys.argv[1]
    sample = build_sample()
    print(f"抽样 {len(sample)} 条（每类最多 10 条）")

    clf = joblib.load(BACKEND / "app/ml/text_action_clf.joblib")
    joblib_pred = clf.predict([t for _, t in sample]).tolist()

    tok = AutoTokenizer.from_pretrained(ap_model, trust_remote_code=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                             bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True)
    base = AutoModelForCausalLM.from_pretrained(ap_model, quantization_config=bnb,
                                                device_map="auto", torch_dtype=torch.bfloat16)
    base.eval()
    # 注意：PeftModel.from_pretrained 会就地改写 base（注入 LoRA 层），
    # 所以必须先跑完 base 的评测再 wrap——否则 "base" 列跑的是微调后的模型。
    tuned = None

    cfg = load_env()
    client = OpenAI(base_url=cfg["EXP5_LLM_BASE_URL"], api_key=cfg["EXP5_LLM_API_KEY"], timeout=60,
                    http_client=httpx.Client(trust_env=False, timeout=60))

    rows = []
    t0 = time.time()
    for i, (gold, text) in enumerate(sample, 1):
        braw, bpred = local_generate(base, tok, text)
        rows.append({"gold": gold, "text": text, "joblib": joblib_pred[i - 1],
                     "base": bpred, "base_raw": braw})
        if i % 20 == 0:
            print(f"  base {i}/{len(sample)}  {time.time()-t0:.0f}s")

    tuned = PeftModel.from_pretrained(base, str(ADAPTER))
    tuned.eval()
    for i, row in enumerate(rows, 1):
        lraw, lpred = local_generate(tuned, tok, row["text"])
        row["lora"], row["lora_raw"] = lpred, lraw
        if i % 20 == 0:
            print(f"  lora {i}/{len(rows)}  {time.time()-t0:.0f}s")

    for row in rows:
        resp = client.chat.completions.create(
            model=cfg["EXP5_LLM_MODEL"], temperature=0, max_tokens=16,
            messages=[{"role": "user", "content": build_prompt(row["text"])}],
        )
        zraw = (resp.choices[0].message.content or "").strip()
        row["api"], row["api_raw"] = parse_label(zraw), zraw
        if i % 20 == 0:
            print(f"  {i}/{len(sample)}  {time.time()-t0:.0f}s")

    def acc(key):
        return round(sum(1 for r in rows if r[key] == r["gold"]) / len(rows), 3)

    payload = {
        "n": len(rows),
        "accuracy": {k: acc(k) for k in ("joblib", "base", "lora", "api")},
        "per_class": {},
        "rows": rows,
    }
    for label in LABELS:
        sub = [r for r in rows if r["gold"] == label]
        if sub:
            payload["per_class"][label] = {k: round(sum(1 for r in sub if r[k] == label) / len(sub), 2)
                                           for k in ("joblib", "base", "lora", "api")}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload["accuracy"], ensure_ascii=False))
    print(json.dumps(payload["per_class"], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())

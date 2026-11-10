# -*- coding: utf-8 -*-
"""段4 出分：同一批 10 道题，考"本地基座（未微调）"与"本地基座 + LoRA 适配器"。

用与训练逐字相同的 prompt（exp5/eval/prompt.py），贪心解码，结果存
  exp5/eval/finetuned.json（含 adapter 结果与本地基座结果、每条原始输出）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))

import torch  # noqa: E402
from peft import PeftModel  # noqa: E402
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig  # noqa: E402

from prompt import build_prompt, parse_label  # noqa: E402

EXAM = REPO / "exp5/data/agent_eval_10.json"
OUT = REPO / "exp5/eval/finetuned.json"
ADAPTER = REPO / "exp5/adapters/qwen3-1.7b-lora"


def strip_think(text: str) -> str:
    """去掉 Qwen3 的 思考块，只看最终答案（判断标准不奖励/不惩罚思考过程）。"""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()


def run(model, tok, items, tag):
    rows = []
    for i, item in enumerate(items, 1):
        base_prompt = tok.apply_chat_template(
            [{"role": "user", "content": build_prompt(item["input"])}],
            tokenize=False, add_generation_prompt=True,
        )
        # 审计修正：Qwen3 默认会先"思考"，48 token 会被截断，
        # 截断处最先出现的类别名往往来自"可选类别"的复述，导致解析错误。
        # 这里用 assistant 前缀预填空思考块，让模型直接出答案（对基座/LoRA 完全一致）。
        prompt = base_prompt + "<think>\n\n</think>\n\n"
        inputs = tok(prompt, return_tensors="pt").to(model.device)
        t0 = time.perf_counter()
        with torch.no_grad():
            out = model.generate(
                **inputs, max_new_tokens=16, do_sample=False,
                pad_token_id=tok.eos_token_id,
            )
        dt = time.perf_counter() - t0
        raw = tok.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
        pred = parse_label(strip_think(raw))
        rows.append({
            "id": i, "gold": item["output"], "text": item["input"],
            "raw": raw, "clean": strip_think(raw), "pred": pred,
            "seconds": round(dt, 2),
        })
        print(f'{tag} {i:2d}. gold={item["output"]:<6} pred={pred or "?":<6} {dt:.2f}s raw={raw.strip()!r}')
    acc = sum(1 for r in rows if r["pred"] == r["gold"]) / len(rows)
    return rows, round(acc, 3)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--adapter", default=str(ADAPTER))
    args = ap.parse_args()

    items = json.loads(EXAM.read_text(encoding="utf-8"))
    tok = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token

    bnb = BitsAndBytesConfig(
        load_in_4bit=True, bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.bfloat16,
    )
    base = AutoModelForCausalLM.from_pretrained(
        args.model, quantization_config=bnb, device_map="auto",
        torch_dtype=torch.bfloat16, trust_remote_code=True,
    )
    base.eval()

    print("=== 本地基座（未微调）===")
    base_rows, base_acc = run(base, tok, items, "base")

    print("\n=== 本地基座 + LoRA ===")
    tuned = PeftModel.from_pretrained(base, args.adapter)
    tuned.eval()
    tuned_rows, tuned_acc = run(tuned, tok, items, "lora")

    payload = {
        "model": args.model, "adapter": args.adapter,
        "n": len(items),
        "local_base_accuracy": base_acc,
        "local_lora_accuracy": tuned_acc,
        "local_base_seconds_mean": round(sum(r["seconds"] for r in base_rows) / len(base_rows), 2),
        "local_lora_seconds_mean": round(sum(r["seconds"] for r in tuned_rows) / len(tuned_rows), 2),
        "base_rows": base_rows, "lora_rows": tuned_rows,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n本地基座 {base_acc:.0%} | 本地+LoRA {tuned_acc:.0%}  -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

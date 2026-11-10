# -*- coding: utf-8 -*-
"""段5.2 量化前后对比：同一模型 + 同一适配器，4-bit vs fp16 的推理延迟与显存。

用法（分两个进程跑，避免显存碎片互相影响）：
  .venv\\Scripts\\python.exe -X utf8 exp5/eval/quant_latency.py --mode 4bit
  .venv\\Scripts\\python.exe -X utf8 exp5/eval/quant_latency.py --mode fp16
结果追加到 exp5/eval/quant_latency.json
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))

import torch  # noqa: E402
from peft import PeftModel  # noqa: E402
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig  # noqa: E402

from prompt import build_prompt  # noqa: E402

MODEL = Path(r"C:\sofeware\AI Api\dsh workspace\fish\work\models\Qwen3-1.7B")
ADAPTER = REPO / "exp5/adapters/qwen3-1.7b-lora"
OUT = REPO / "exp5/eval/quant_latency.json"
TEXTS = [
    "沃特森上罚球线！！",
    "拿球又走步了！！",
    "骑士换人了！！海佐尼亚上来了！！",
    "贺思瑶断球！！",
    "布莱恩特协防大帽！！",
    "埃纳鲁纳篮板！给快下海佐尼亚！！",
    "分球贾明儒！！",
    "托马斯左侧接球三分！",
    "第一节结束！山西领先11分！",
    "借掩护加速突破！",
]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["4bit", "fp16"], required=True)
    args = ap.parse_args()

    tok = AutoTokenizer.from_pretrained(str(MODEL), trust_remote_code=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token

    t0 = time.perf_counter()
    if args.mode == "4bit":
        bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                 bnb_4bit_use_double_quant=True,
                                 bnb_4bit_compute_dtype=torch.bfloat16)
        model = AutoModelForCausalLM.from_pretrained(
            str(MODEL), quantization_config=bnb, device_map="auto",
            torch_dtype=torch.bfloat16, trust_remote_code=True)
    else:
        model = AutoModelForCausalLM.from_pretrained(
            str(MODEL), device_map="auto", torch_dtype=torch.float16, trust_remote_code=True)
    model = PeftModel.from_pretrained(model, str(ADAPTER))
    model.eval()
    load_s = time.perf_counter() - t0
    torch.cuda.reset_peak_memory_stats()

    times = []
    for text in TEXTS:
        prompt = tok.apply_chat_template(
            [{"role": "user", "content": build_prompt(text)}],
            tokenize=False, add_generation_prompt=True) + "<think>\n\n</think>\n\n"
        inputs = tok(prompt, return_tensors="pt").to(model.device)
        with torch.no_grad():
            t1 = time.perf_counter()
            model.generate(**inputs, max_new_tokens=8, do_sample=False,
                           pad_token_id=tok.eos_token_id)
            times.append(round((time.perf_counter() - t1) * 1000, 1))

    mean_ms = round(st.mean(times), 1)
    p95 = sorted(times)[max(0, int(round(0.95 * (len(times) - 1))))]
    peak_gb = round(torch.cuda.max_memory_allocated() / 1024**3, 2)
    rec = {
        "mode": args.mode, "load_seconds": round(load_s, 1),
        "mean_ms": mean_ms, "p95_ms": p95, "median_ms": round(st.median(times), 1),
        "min_ms": min(times), "max_ms": max(times),
        "peak_vram_gb": peak_gb, "per_item_ms": times,
        "gpu": torch.cuda.get_device_name(0),
    }
    print(json.dumps({k: v for k, v in rec.items() if k != "per_item_ms"}, ensure_ascii=False))

    data = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    data[args.mode] = rec
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

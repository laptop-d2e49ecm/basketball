# -*- coding: utf-8 -*-
"""段5.2 补充：**Agent 链路**的量化对比（不是模型单条推理）。

做法：用 /api/v1/agent/chat 真实跑 10 次分类问题，读响应里的
`tool_calls[].elapsed_ms`（工具内部耗时）与 `elapsed_ms`（端到端），
分别在 EXP5_LORA_QUANT=4bit / fp16 两种后端下各跑一轮。

用法（先把后端以对应量化方式启动）：
  python exp5/eval/agent_latency.py --tag 4bit
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import sys
import time
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "exp5/eval/agent_latency_quant.json"
URL = "http://127.0.0.1:8000/api/v1/agent/chat"
TEXTS = [
    "帮我分类这句解说：库里外线出手，三分命中！",
    "这句是什么动作：骑士换人了，海佐尼亚上来了",
    "分类一下：贺思瑶断球！",
    "这句解说属于什么：布莱恩特协防大帽！",
    "判断类别：埃纳鲁纳篮板！给快下海佐尼亚！",
    "分类：分球贾明儒！",
    "这句呢：第一节结束！山西领先11分！",
    "判断动作：借掩护加速突破！",
    "分类：沃特森上罚球线！",
    "这句是什么：拿球又走步了！",
]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    args = ap.parse_args()

    client = httpx.Client(timeout=180, trust_env=False)
    # 预热一次（模型懒加载 + 首token），不计入统计
    warm = client.post(URL, json={"message": "帮我分类这句解说：库里三分命中！"})
    print("warm", warm.status_code)

    rows = []
    for i, text in enumerate(TEXTS, 1):
        t0 = time.perf_counter()
        r = client.post(URL, json={"message": text})
        wall = round((time.perf_counter() - t0) * 1000)
        body = r.json()
        res = body.get("result") or {}
        tools = res.get("tool_calls") or []
        tool_ms = next((t.get("elapsed_ms") for t in tools if t.get("tool") == "commentary_classify"), None)
        rows.append({
            "text": text, "status": r.status_code,
            "tool_ms": tool_ms, "e2e_ms": res.get("elapsed_ms") or wall,
            "answer": (res.get("agent") or "")[:40],
        })
        print(f"{i:2d}. {r.status_code} tool={tool_ms} e2e={rows[-1]['e2e_ms']}ms")

    tool_vals = [r["tool_ms"] for r in rows if r["tool_ms"]]
    e2e_vals = [r["e2e_ms"] for r in rows]
    rec = {
        "tag": args.tag, "n": len(rows),
        "tool_mean_ms": round(st.mean(tool_vals), 1) if tool_vals else None,
        "tool_std_ms": round(st.stdev(tool_vals), 1) if len(tool_vals) > 1 else 0,
        "tool_p95_ms": sorted(tool_vals)[max(0, int(round(0.95 * (len(tool_vals) - 1))))] if tool_vals else None,
        "e2e_mean_ms": round(st.mean(e2e_vals), 1),
        "e2e_p95_ms": sorted(e2e_vals)[max(0, int(round(0.95 * (len(e2e_vals) - 1))))],
        "rows": rows,
    }
    data = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    data[args.tag] = rec
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in rec.items() if k != "rows"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

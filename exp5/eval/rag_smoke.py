# -*- coding: utf-8 -*-
"""RAG 检索工具冒烟：验证 retrieve_commentary 的检索质量与路由正确性。

用法（仓库根目录）：.venv\\Scripts\\python.exe -X utf8 exp5/eval/rag_smoke.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "exp4" / "complete_web_system" / "backend"))

from app.agent.graph import build_agent  # noqa: E402

CASES = [
    ("检索问答", "突破上篮得分的时候，真人解说一般会怎么说？", "retrieve_commentary"),
    ("生成解说", "给我来一句三分球绝杀的解说！", "retrieve_commentary"),
]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    agent = build_agent()
    ok_all = True
    for name, q, expect in CASES:
        started = time.perf_counter()
        result = agent.invoke({"messages": [{"role": "user", "content": q}]})
        called = [
            c.get("name", "")
            for m in result["messages"]
            if getattr(m, "type", "") == "ai" and getattr(m, "tool_calls", None)
            for c in m.tool_calls
        ]
        ok = expect in called
        ok_all &= ok
        print(f"\n===== {name} [{'PASS' if ok else 'FAIL'}] {time.perf_counter() - started:.1f}s =====")
        print(f"用户：{q}")
        print(f"调用：{called}")
        print(f"AI：{result['messages'][-1].content}")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())

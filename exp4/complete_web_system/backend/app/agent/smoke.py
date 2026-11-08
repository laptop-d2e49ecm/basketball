# -*- coding: utf-8 -*-
"""Agent 冒烟脚本（任务书 5.3.2 单轮测试）。

用法（backend 目录下）：
    python -m app.agent.smoke
或仓库根目录：python exp5/smoke_agent.py
"""
from __future__ import annotations

import sys

from app.agent.graph import build_agent

SCENARIOS = [
    ("场景2·文本分类", "帮我看看这句解说是什么动作：库里外线出手，三分命中！"),
    ("场景1·图像检测", "f000005 这张图里有几个球员？"),
    ("免工具·概念题", "用一句话说说 AI 解说员是干什么的？"),
]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print("正在初始化 Agent（首次会加载 ONNX 模型，稍等）...")
    agent = build_agent()

    passed = 0
    for name, question in SCENARIOS:
        print(f"\n===== {name} =====")
        print(f"用户：{question}")
        try:
            result = agent.invoke({"messages": [{"role": "user", "content": question}]})
        except Exception as exc:  # noqa: BLE001
            print(f"[FAIL] 调用异常：{type(exc).__name__}: {exc}")
            continue
        for msg in result["messages"]:
            if getattr(msg, "type", "") == "ai" and getattr(msg, "tool_calls", None):
                for call in msg.tool_calls:
                    print(f"  🔧 调用工具 {call['name']}({call.get('args', {})})")
        if not any(getattr(m, "tool_calls", None) for m in result["messages"]):
            print("  （未调用工具）")
        print(f"AI：{result['messages'][-1].content}")
        passed += 1

    print(f"\n冒烟结果：{passed}/{len(SCENARIOS)} 个场景跑通")
    return 0 if passed == len(SCENARIOS) else 1


if __name__ == "__main__":
    sys.exit(main())

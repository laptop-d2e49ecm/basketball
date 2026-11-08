# -*- coding: utf-8 -*-
"""10 轮工具调用准确率评估（任务书 5.4.3 / 报告硬指标：>=90%）。

用法（仓库根目录）：
    .venv\\Scripts\\python.exe -X utf8 exp5/eval/tool_accuracy.py
输出：逐轮判定表 + 准确率，结果存 exp5/eval/tool_accuracy_result.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "exp4" / "complete_web_system" / "backend"))

from app.agent.graph import build_agent  # noqa: E402

# 10 轮测试：每轮标注"应选工具"（none = 应直接回答不调工具）
ROUNDS: list[dict[str, str]] = [
    {"q": "f000005 这张图里有几个球员？", "expect": "player_detect"},
    {"q": "帮我检测一下 f000040 这张图有没有球员", "expect": "player_detect"},
    {"q": "f000025 图里的人数是多少？", "expect": "player_detect"},
    {"q": "这句解说什么动作：詹姆斯突破分球，底角三分命中！", "expect": "commentary_classify"},
    {"q": "分类一下这条解说：抢断之后一条龙快攻上篮得手", "expect": "commentary_classify"},
    {"q": "这条文字是什么类别：教练请求了暂停，球队布置战术", "expect": "commentary_classify"},
    {"q": "库里又抢到一个前场篮板！这句解说属于什么动作？", "expect": "commentary_classify"},
    {"q": "再看看 f000005，帮我检测一下球员", "expect": "player_detect"},
    {"q": "AI 解说员是干什么的？", "expect": "none"},
    {"q": "你们这个系统能做些什么？", "expect": "none"},
]


def tools_of(messages: list) -> list[str]:
    names = []
    for msg in messages:
        if getattr(msg, "type", "") == "ai" and getattr(msg, "tool_calls", None):
            names.extend(call.get("name", "") for call in msg.tool_calls)
    return names


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    agent = build_agent()

    records = []
    correct = 0
    for i, case in enumerate(ROUNDS, 1):
        started = time.perf_counter()
        try:
            result = agent.invoke({"messages": [{"role": "user", "content": case["q"]}]})
            called = tools_of(result["messages"])
        except Exception as exc:  # noqa: BLE001
            called = [f"ERROR:{type(exc).__name__}"]
        elapsed = round(time.perf_counter() - started, 1)

        if case["expect"] == "none":
            ok = len(called) == 0
        else:
            ok = case["expect"] in called
        correct += ok
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] 第{i:2d}轮  期望 {case['expect']:20s} 实际 {called}  {elapsed}s")
        records.append({"round": i, "q": case["q"], "expect": case["expect"],
                        "called": called, "ok": ok, "seconds": elapsed})

    accuracy = correct / len(ROUNDS)
    print(f"\n工具选择准确率：{correct}/{len(ROUNDS)} = {accuracy:.0%}（任务书目标 >=90%）")

    out = Path(__file__).with_name("tool_accuracy_result.json")
    out.write_text(json.dumps({
        "tested_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "accuracy": accuracy,
        "records": records,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"结果已存：{out}")
    return 0 if accuracy >= 0.9 else 1


if __name__ == "__main__":
    sys.exit(main())

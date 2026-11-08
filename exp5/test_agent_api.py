# -*- coding: utf-8 -*-
"""Agent API 接口测试（契约 exp5/CONTRACT.md §8 用例表的可执行版）。

前置：后端已启动（backend 目录 uvicorn app.main:app --port 8000）。
运行：.venv\\Scripts\\python.exe -X utf8 exp5/test_agent_api.py
"""
from __future__ import annotations

import sys

import httpx

URL = "http://127.0.0.1:8000/api/v1/agent/chat"
client = httpx.Client(timeout=120)

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}  {detail}")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    # 用例1：首轮图像对话（任务书场景1）
    r1 = client.post(URL, json={"message": "f000005 这张图里有几个球员？"})
    body1 = r1.json()
    tools1 = [c["tool"] for c in (body1.get("result") or {}).get("tool_calls", [])]
    ok1 = r1.status_code == 200 and body1.get("code") == 0 and "player_detect" in tools1
    check("场景1·首轮图像", ok1,
          f"HTTP {r1.status_code} | 工具 {tools1} | 回复片段：{(body1.get('result') or {}).get('agent', '')[:60]}")
    session_id = (body1.get("result") or {}).get("session_id", "")

    # 用例2：多轮续聊（任务书场景3：同 session 追问）
    r2 = client.post(URL, json={"session_id": session_id, "message": "再看看 f000025 有几个人？"})
    body2 = r2.json()
    tools2 = [c["tool"] for c in (body2.get("result") or {}).get("tool_calls", [])]
    ok2 = r2.status_code == 200 and body2.get("code") == 0 and "player_detect" in tools2
    check("场景3·多轮续聊", ok2,
          f"HTTP {r2.status_code} | 工具 {tools2} | 回复片段：{(body2.get('result') or {}).get('agent', '')[:60]}")

    # 用例3：文本分类（任务书场景2）
    r3 = client.post(URL, json={"message": "帮我分类这句解说：抢断之后一条龙快攻上篮得手！"})
    body3 = r3.json()
    tools3 = [c["tool"] for c in (body3.get("result") or {}).get("tool_calls", [])]
    ok3 = r3.status_code == 200 and body3.get("code") == 0 and "commentary_classify" in tools3
    check("场景2·文本分类", ok3,
          f"HTTP {r3.status_code} | 工具 {tools3} | 回复片段：{(body3.get('result') or {}).get('agent', '')[:60]}")

    # 用例4：空消息 → 400
    r4 = client.post(URL, json={"message": ""})
    body4 = r4.json()
    check("异常·空消息400", r4.status_code == 400 and body4.get("code") == 400, f"HTTP {r4.status_code} | {body4.get('msg', '')[:50]}")

    # 用例5：坏 session → 404
    r5 = client.post(URL, json={"session_id": "sess_不存在", "message": "你好"})
    body5 = r5.json()
    check("异常·坏会话404", r5.status_code == 404 and body5.get("code") == 404, f"HTTP {r5.status_code} | {body5.get('msg', '')[:50]}")

    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\n接口测试：{passed}/{len(results)} 通过")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())

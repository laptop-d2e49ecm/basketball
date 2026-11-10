# -*- coding: utf-8 -*-
"""段5.4 异常注入：验证契约 §4 的错误码映射（超时 504 / 限流 429 / 空消息 400 / 坏会话 404）。

用 TestClient + 伪造 agent，可控地触发 LLM 层的各类异常；
另有 `--real-bad-key` 走真实 HTTP（需要后端以错误 key 启动）。

用法：
  .venv\\Scripts\\python.exe -X utf8 exp5/eval/error_injection.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "exp4/complete_web_system/backend"
sys.path.insert(0, str(BACKEND))

OUT = REPO / "exp5/eval/error_injection.json"


class BoomAgent:
    """可控的假 Agent：按需抛不同异常。"""

    def __init__(self, exc: Exception):
        self.exc = exc

    def invoke(self, _payload):
        raise self.exc


class OkAgent:
    def invoke(self, _payload):
        return {"messages": [type("M", (), {"content": "ok", "type": "ai", "tool_calls": None})()]}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    from fastapi.testclient import TestClient

    from app.main import app

    results = []
    with TestClient(app, raise_server_exceptions=False) as client:
        url = "/api/v1/agent/chat"

        # 基线：正常返回
        app.state.agent = OkAgent()
        r = client.post(url, json={"message": "你好"})
        results.append({"case": "正常对话", "expect": 200, "got": r.status_code, "body": r.json()})

        # 超时 → 504
        app.state.agent = BoomAgent(TimeoutError("Request timed out."))
        r = client.post(url, json={"message": "f000005 有几个人"})
        results.append({"case": "LLM 超时", "expect": 504, "got": r.status_code, "body": r.json()})

        # 限流 → 429
        app.state.agent = BoomAgent(Exception("Error code: 429 - rate limit exceeded"))
        r = client.post(url, json={"message": "再来一句解说"})
        results.append({"case": "限流 429", "expect": 429, "got": r.status_code, "body": r.json()})

        # 其他异常 → 500
        app.state.agent = BoomAgent(RuntimeError("connection reset"))
        r = client.post(url, json={"message": "随便问问"})
        results.append({"case": "上游连接失败", "expect": 500, "got": r.status_code, "body": r.json()})

        # 空消息 → 400
        app.state.agent = OkAgent()
        r = client.post(url, json={"message": ""})
        results.append({"case": "空消息", "expect": 400, "got": r.status_code, "body": r.json()})

        # 坏会话 → 404
        r = client.post(url, json={"session_id": "sess_not_exist", "message": "hi"})
        results.append({"case": "坏 session", "expect": 404, "got": r.status_code, "body": r.json()})

    ok = 0
    for item in results:
        passed = item["got"] == item["expect"]
        ok += passed
        print(f'[{"PASS" if passed else "FAIL"}] {item["case"]:<12} 期望 {item["expect"]} 实际 {item["got"]}'
              f' | {str(item["body"].get("msg", ""))[:40]}')
    OUT.write_text(json.dumps({"passed": ok, "total": len(results), "cases": results},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{ok}/{len(results)} 通过 -> {OUT}")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())

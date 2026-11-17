# -*- coding: utf-8 -*-
"""Agent 对话 API 的最小单测：块列表内容归一（新中转 gpt-6.1-sol 行为）。"""
from __future__ import annotations

from types import SimpleNamespace

from app.api import agent as agent_api
from app.api.agent import AgentChatRequest, _history_to_messages


class _FakeAgent:
    def __init__(self, content):
        self._content = content

    def invoke(self, payload):
        return {"messages": [
            SimpleNamespace(type="tool", content="任务 task123 的关键事件：\n[0.0s] play，耗时 5.0ms"),
            SimpleNamespace(type="ai", tool_calls=[], content=self._content),
        ]}


def _patch_store(monkeypatch):
    saved: list[dict] = []

    monkeypatch.setattr(agent_api.agent_sessions, "new_session", lambda: "sess_test")
    monkeypatch.setattr(agent_api.agent_sessions, "load_history", lambda sid: [])
    monkeypatch.setattr(
        agent_api.agent_sessions, "append_history", lambda sid, entries: saved.extend(entries)
    )
    monkeypatch.setattr(agent_api, "_write_log", lambda *a, **k: None)
    return saved


def test_agent_chat_extracts_text_from_block_content(monkeypatch):
    """新中转把回复放在 [{'type':'text',...}] 块里：接口必须提取纯文本，不能泄露块结构。"""
    monkeypatch.setattr(
        agent_api,
        "_get_agent",
        lambda request: _FakeAgent([
            {"type": "reasoning", "encrypted_content": "gAAAAAB1secret"},
            {"type": "text", "text": "共 3 个事件，最激烈的是第二节篮下争抢。"},
        ]),
    )
    saved = _patch_store(monkeypatch)

    envelope = agent_api.agent_chat(AgentChatRequest(message="有哪些事件？"), request=None)
    text = envelope.result["agent"]
    assert text == "共 3 个事件，最激烈的是第二节篮下争抢。"
    assert "gAAAAAB" not in text and "reasoning" not in text
    assert saved[1]["content"] == text  # 存库内容同样是纯文本


def test_agent_chat_plain_string_content_untouched(monkeypatch):
    monkeypatch.setattr(agent_api, "_get_agent", lambda request: _FakeAgent("普通字符串回复。"))
    _patch_store(monkeypatch)

    envelope = agent_api.agent_chat(AgentChatRequest(message="问一句"), request=None)
    assert envelope.result["agent"] == "普通字符串回复。"


def test_history_to_messages_normalizes_stored_block_list():
    """历史里残留的列表内容也应归一成纯文本再回传模型。"""
    history = [
        {"role": "user", "content": "问"},
        {"role": "agent", "content": [{"type": "text", "text": "答：两次三分出手。"}], "tool_calls": []},
    ]
    messages = _history_to_messages(history)
    assert messages == [
        {"role": "user", "content": "问"},
        {"role": "assistant", "content": "答：两次三分出手。"},
    ]

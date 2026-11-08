# -*- coding: utf-8 -*-
"""Agent 会话存储（断点续聊）：SQLite 表 agent_sessions，与实验4 tasks 同库（契约 7.1）。

history 为 JSON 数组，字段命名对齐任务书重点（user / agent / tool_calls）：
  [{"role": "user", "content": "..."},
   {"role": "agent", "content": "...", "tool_calls": [...]}]
"""
from __future__ import annotations

import json
import secrets
import time
from typing import Any

from app.db.database import connection

_TABLE_READY = False


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def ensure_table() -> None:
    global _TABLE_READY
    if _TABLE_READY:
        return
    with connection() as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_sessions (
                session_id TEXT PRIMARY KEY,
                history TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
    _TABLE_READY = True


def new_session() -> str:
    ensure_table()
    session_id = f"sess_{secrets.token_hex(6)}"
    now = _now()
    with connection() as db:
        db.execute(
            "INSERT INTO agent_sessions (session_id, history, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (session_id, "[]", now, now),
        )
    return session_id


def load_history(session_id: str) -> list[dict[str, Any]] | None:
    """返回会话历史；会话不存在返回 None（API 层据此抛 404）。"""
    ensure_table()
    with connection() as db:
        row = db.execute(
            "SELECT history FROM agent_sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
    if row is None:
        return None
    try:
        history = json.loads(row["history"])
    except json.JSONDecodeError:
        return []
    return history if isinstance(history, list) else []


def append_history(session_id: str, entries: list[dict[str, Any]]) -> None:
    ensure_table()
    with connection() as db:
        row = db.execute(
            "SELECT history FROM agent_sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row is None:
            return
        history = json.loads(row["history"])
        history.extend(entries)
        db.execute(
            "UPDATE agent_sessions SET history = ?, updated_at = ? WHERE session_id = ?",
            (json.dumps(history, ensure_ascii=False), _now(), session_id),
        )

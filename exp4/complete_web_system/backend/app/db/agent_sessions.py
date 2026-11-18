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
                task_id TEXT,
                history TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        columns = {row["name"] for row in db.execute("PRAGMA table_info(agent_sessions)")}
        if "task_id" not in columns:
            db.execute("ALTER TABLE agent_sessions ADD COLUMN task_id TEXT")
        db.execute("CREATE INDEX IF NOT EXISTS ix_agent_sessions_task_updated ON agent_sessions(task_id, updated_at DESC)")
    _TABLE_READY = True


def new_session(task_id: str | None = None) -> str:
    ensure_table()
    session_id = f"sess_{secrets.token_hex(6)}"
    now = _now()
    with connection() as db:
        db.execute(
            "INSERT INTO agent_sessions (session_id, task_id, history, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (session_id, task_id, "[]", now, now),
        )
    return session_id


def get_session(session_id: str) -> dict[str, Any] | None:
    ensure_table()
    with connection() as db:
        row = db.execute("SELECT * FROM agent_sessions WHERE session_id = ?", (session_id,)).fetchone()
    if row is None:
        return None
    try:
        history = json.loads(row["history"])
    except (ValueError, TypeError):
        history = []
    if not isinstance(history, list):
        history = []
    return {
        "session_id": row["session_id"], "task_id": row["task_id"],
        "history": history, "created_at": row["created_at"], "updated_at": row["updated_at"],
    }


def list_sessions(task_id: str | None = None) -> list[dict[str, Any]]:
    ensure_table()
    with connection() as db:
        if task_id is None:
            rows = db.execute("SELECT * FROM agent_sessions ORDER BY updated_at DESC, rowid DESC").fetchall()
        else:
            rows = db.execute("SELECT * FROM agent_sessions WHERE task_id = ? ORDER BY updated_at DESC, rowid DESC", (task_id,)).fetchall()
    result = []
    for row in rows:
        try:
            history = json.loads(row["history"])
        except (ValueError, TypeError):
            history = []
        if not isinstance(history, list):
            history = []
        title = next((str(item.get("content", ""))[:60] for item in history if item.get("role") == "user"), "新对话")
        result.append({"session_id": row["session_id"], "task_id": row["task_id"],
                       "title": title, "message_count": len(history),
                       "created_at": row["created_at"], "updated_at": row["updated_at"]})
    return result


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

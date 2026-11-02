from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from app.db.database import connection


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _decode(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    result = dict(row)
    result["task_id"] = result["id"]
    result["metadata"] = json.loads(result.pop("metadata_json", "{}"))
    return result


def _notify(db: Any, task_id: str, payload: dict[str, Any]) -> None:
    db.execute(
        "INSERT INTO task_notifications(task_id, payload_json, created_at) VALUES (?, ?, ?)",
        (task_id, json.dumps(payload, ensure_ascii=False), _now()),
    )


def notify_task(task_id: str, payload: dict[str, Any]) -> None:
    """Append a WebSocket notification without changing task fields."""
    with connection() as db:
        _notify(db, task_id, payload)


def create_task(*, task_id: str, video_name: str, video_path: str, metadata: dict[str, Any]) -> None:
    with connection() as db:
        db.execute(
            """INSERT INTO tasks
               (id, video_name, video_path, metadata_json, status, stage, progress, created_at)
               VALUES (?, ?, ?, ?, 'pending', 'queued', 0, ?)""",
            (task_id, video_name, video_path, json.dumps(metadata, ensure_ascii=False), _now()),
        )
        _notify(db, task_id, {"type": "progress", "stage": "queued", "progress": 0})


def get_task(task_id: str) -> dict[str, Any] | None:
    with connection() as db:
        return _decode(db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone())


def list_tasks(*, limit: int, offset: int) -> list[dict[str, Any]]:
    with connection() as db:
        rows = db.execute(
            "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset)
        ).fetchall()
    return [_decode(row) for row in rows if row is not None]


def measured_average_infer_ms() -> float | None:
    """Return the frame-weighted mean from completed video tasks, if available."""
    with connection() as db:
        row = db.execute(
            """SELECT SUM(avg_infer_ms * frames_done) / NULLIF(SUM(frames_done), 0) AS avg_ms
               FROM tasks
               WHERE status = 'ready' AND avg_infer_ms IS NOT NULL AND frames_done > 0"""
        ).fetchone()
    value = row["avg_ms"] if row is not None else None
    return float(value) if value is not None else None


def claim_next_task() -> dict[str, Any] | None:
    with connection() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM tasks WHERE status = 'pending' ORDER BY created_at LIMIT 1").fetchone()
        if row is None:
            return None
        task_id = row["id"]
        db.execute(
            "UPDATE tasks SET status = 'running', stage = 'decoding', progress = 0 WHERE id = ?",
            (task_id,),
        )
        _notify(db, task_id, {"type": "progress", "stage": "decoding", "progress": 0})
        updated = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return _decode(updated)


def claim_task_by_id(task_id: str) -> dict[str, Any] | None:
    """Atomically claim one pending task dispatched through Celery."""
    with connection() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT * FROM tasks WHERE id = ? AND status = 'pending'",
            (task_id,),
        ).fetchone()
        if row is None:
            return None
        db.execute(
            "UPDATE tasks SET status = 'running', stage = 'decoding', progress = 0 WHERE id = ?",
            (task_id,),
        )
        _notify(db, task_id, {"type": "progress", "stage": "decoding", "progress": 0})
        updated = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return _decode(updated)


def list_pending_task_ids() -> list[str]:
    with connection() as db:
        rows = db.execute("SELECT id FROM tasks WHERE status = 'pending' ORDER BY created_at").fetchall()
    return [str(row["id"]) for row in rows]


def delete_task(task_id: str) -> None:
    """Remove a task that could not be submitted to the configured queue."""
    with connection() as db:
        db.execute("DELETE FROM task_notifications WHERE task_id = ?", (task_id,))
        db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))


def recover_running_tasks() -> None:
    with connection() as db:
        rows = db.execute("SELECT id FROM tasks WHERE status = 'running'").fetchall()
        for row in rows:
            task_id = row["id"]
            db.execute(
                "UPDATE tasks SET status = 'pending', stage = 'queued', progress = 0, error = NULL WHERE id = ?",
                (task_id,),
            )
            _notify(db, task_id, {"type": "progress", "stage": "queued", "progress": 0})


def update_task(task_id: str, *, notify: dict[str, Any] | None = None, **fields: Any) -> None:
    allowed = {
        "status", "stage", "progress", "error", "finished_at", "frames_total",
        "frames_done", "avg_infer_ms", "total_seconds",
    }
    updates = {key: value for key, value in fields.items() if key in allowed}
    if not updates:
        return
    assignments = ", ".join(f"{key} = ?" for key in updates)
    with connection() as db:
        db.execute(
            f"UPDATE tasks SET {assignments} WHERE id = ?",
            (*updates.values(), task_id),
        )
        if notify is not None:
            _notify(db, task_id, notify)


def update_task_metadata(task_id: str, **fields: Any) -> None:
    with connection() as db:
        row = db.execute("SELECT metadata_json FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            return
        metadata = json.loads(row["metadata_json"] or "{}")
        metadata.update(fields)
        db.execute(
            "UPDATE tasks SET metadata_json = ? WHERE id = ?",
            (json.dumps(metadata, ensure_ascii=False), task_id),
        )


def notifications_after(task_id: str, after_id: int) -> list[dict[str, Any]]:
    with connection() as db:
        rows = db.execute(
            "SELECT id, payload_json FROM task_notifications WHERE task_id = ? AND id > ? ORDER BY id",
            (task_id, after_id),
        ).fetchall()
    return [{"id": row["id"], **json.loads(row["payload_json"])} for row in rows]

"""批量图像检测的轻量异步执行（内存任务表 + FastAPI BackgroundTasks）。

定位：本侧"异步任务处理"演示线（任务书 4.2.3 大文件/批量场景的最小实现）；
视频等重型异步任务走队友的 Worker+SQLite 线（见 EXP4_PLAN.md §三）。
"""
from __future__ import annotations

import threading
import uuid

from ..core.errors import NotFoundError

_lock = threading.Lock()
_tasks: dict[str, dict] = {}


def create(total: int) -> str:
    task_id = uuid.uuid4().hex[:12]
    with _lock:
        _tasks[task_id] = {
            "task_id": task_id, "status": "running", "done": 0, "total": total,
            "results": [],
        }
    return task_id


def get(task_id: str) -> dict:
    with _lock:
        if task_id not in _tasks:
            raise NotFoundError(f"批量任务不存在: {task_id}")
        return _tasks[task_id]


def run_batch(detector, task_id: str, payloads: list[tuple[str, bytes]]) -> None:
    """后台逐张推理并更新任务表（BackgroundTasks 线程中执行）。"""
    for filename, data in payloads:
        item = {"filename": filename, "ok": False, "player_count": None, "error": None}
        try:
            r = detector.api_detect(data)
            item.update(ok=True, player_count=r["player_count"])
        except Exception as e:  # noqa: BLE001
            item["error"] = str(e)[:200]
        with _lock:
            t = _tasks.get(task_id)
            if t is None:
                return
            t["results"].append(item)
            t["done"] += 1
    with _lock:
        if task_id in _tasks:
            _tasks[task_id]["status"] = "done"

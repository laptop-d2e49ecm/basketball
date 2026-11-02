from __future__ import annotations

import threading
import uuid

from app.core.errors import NotFoundError


class ImageBatchStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tasks: dict[str, dict] = {}

    def create(self, total: int) -> str:
        task_id = uuid.uuid4().hex[:12]
        with self._lock:
            self._tasks[task_id] = {
                "task_id": task_id,
                "status": "running",
                "done": 0,
                "total": total,
                "results": [],
            }
        return task_id

    def get(self, task_id: str) -> dict:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise NotFoundError(f"批量检测任务不存在：{task_id}")
            return {**task, "results": [dict(item) for item in task["results"]]}

    def run(self, detector, task_id: str, payloads: list[tuple[str, bytes]]) -> None:
        for filename, data in payloads:
            result = {"filename": filename, "ok": False, "player_count": None, "error": None}
            try:
                detection = detector.api_detect(data)
                result.update(ok=True, player_count=detection["player_count"])
            except Exception as exc:  # Keep a bad item from aborting the rest of the batch.
                result["error"] = str(exc)[:200]

            with self._lock:
                task = self._tasks.get(task_id)
                if task is None:
                    return
                task["results"].append(result)
                task["done"] += 1

        with self._lock:
            task = self._tasks.get(task_id)
            if task is not None:
                task["status"] = "done"


batch_store = ImageBatchStore()

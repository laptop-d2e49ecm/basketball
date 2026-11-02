from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from ultralytics import YOLO

from app.core.config import settings
from app.db import task_repo
from app.db.database import initialize_database
from worker.video_service import process_task

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("basketball-worker")


def main() -> None:
    if settings.task_backend != "worker":
        raise SystemExit(
            "TASK_BACKEND=celery is active; start the Celery worker with "
            "'celery -A worker.celery_app:celery_app worker --pool=solo' instead."
        )

    settings.runs_dir.mkdir(parents=True, exist_ok=True)
    initialize_database()
    task_repo.recover_running_tasks()
    if not settings.model_path.is_file():
        raise FileNotFoundError(f"模型权重不存在：{settings.model_path}")
    logger.info("Loading model from %s", settings.model_path)
    model = YOLO(str(settings.model_path))
    logger.info("Worker is ready; polling for tasks")

    while True:
        task = task_repo.claim_next_task()
        if task is None:
            time.sleep(settings.worker_poll_seconds)
            continue
        logger.info("Processing task %s", task["id"])
        try:
            process_task(task, model)
        except Exception as exc:
            logger.exception("Task %s failed", task["id"])
            task_repo.update_task(
                task["id"],
                status="failed",
                stage="failed",
                error=str(exc),
                finished_at=datetime.now(UTC).isoformat(),
                notify={"type": "failed", "error": str(exc)},
            )


if __name__ == "__main__":
    main()

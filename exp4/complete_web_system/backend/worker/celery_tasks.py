from __future__ import annotations

import logging
from datetime import UTC, datetime

from celery.signals import worker_ready
from ultralytics import YOLO

from app.core.config import settings
from app.db import task_repo
from app.db.database import initialize_database
from worker.celery_app import VIDEO_TASK_NAME, celery_app
from worker.video_service import process_task

logger = logging.getLogger("basketball-celery-worker")
_model: YOLO | None = None


def _get_model() -> YOLO:
    global _model
    if _model is None:
        if not settings.model_path.is_file():
            raise FileNotFoundError(f"模型权重不存在：{settings.model_path}")
        logger.info("Loading model from %s", settings.model_path)
        _model = YOLO(str(settings.model_path))
    return _model


@celery_app.task(name=VIDEO_TASK_NAME, ignore_result=True)
def process_video_task(task_id: str) -> None:
    initialize_database()
    task = task_repo.claim_task_by_id(task_id)
    if task is None:
        logger.info("Skipping task %s because it is no longer pending", task_id)
        return

    try:
        process_task(task, _get_model())
    except Exception as exc:
        logger.exception("Celery task %s failed", task_id)
        task_repo.update_task(
            task_id,
            status="failed",
            stage="failed",
            error=str(exc),
            finished_at=datetime.now(UTC).isoformat(),
            notify={"type": "failed", "error": str(exc)},
        )
        raise


@worker_ready.connect
def recover_pending_video_tasks(sender, **_: object) -> None:
    """Recover SQLite tasks after a Celery worker restart and put them back on Redis."""
    initialize_database()
    task_repo.recover_running_tasks()
    for task_id in task_repo.list_pending_task_ids():
        sender.app.send_task(VIDEO_TASK_NAME, args=[task_id], queue="basketball.video")

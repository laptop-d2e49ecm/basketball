from __future__ import annotations

from celery import Celery

from app.core.config import settings

VIDEO_TASK_NAME = "worker.process_video_task"

celery_app = Celery(
    "basketball_video",
    broker=settings.celery_broker_url,
    include=["worker.celery_tasks"],
)
celery_app.conf.update(
    task_default_queue="basketball.video",
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_ignore_result=True,
    task_publish_retry=False,
    broker_connection_retry_on_startup=True,
    broker_connection_timeout=5,
    worker_prefetch_multiplier=1,
)


def enqueue_video_task(task_id: str) -> None:
    celery_app.send_task(VIDEO_TASK_NAME, args=[task_id], queue="basketball.video")

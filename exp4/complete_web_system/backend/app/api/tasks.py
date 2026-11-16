from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse

from app.core.config import settings
from app.db import task_repo
from app.schemas.envelope import ApiEnvelope
from app.schemas.tasks import EventItem, TaskCreated, TaskListItem, TaskPreviewStatus, TaskStatus
from app.services.video_preview import (
    get_preview_file,
    get_preview_state,
    remove_preview_task_data,
    start_preview_generation,
)

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


def _load_jsonl(path: Path, *, t_start: float | None = None, t_end: float | None = None) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line)
            timestamp = row.get("t_ms", 0) / 1000
            if t_start is not None and timestamp < t_start:
                continue
            if t_end is not None and timestamp > t_end:
                continue
            rows.append(row)
    return rows


@router.post("", response_model=ApiEnvelope[TaskCreated], status_code=status.HTTP_202_ACCEPTED)
def create_task(
    file: UploadFile = File(...),
    video_name: str | None = Form(default=None),
    team1: str | None = Form(default=None),
    team2: str | None = Form(default=None),
    score1: str | None = Form(default=None),
    score2: str | None = Form(default=None),
) -> ApiEnvelope[TaskCreated]:
    original_name = Path(file.filename or "").name
    if Path(original_name).suffix.lower() != ".mp4":
        raise HTTPException(status_code=400, detail="MVP 目前仅接受 MP4 视频")
    display_name = (video_name or "").strip()[:120] or original_name

    task_id = uuid.uuid4().hex
    task_dir = settings.runs_dir / task_id
    task_dir.mkdir(parents=True, exist_ok=False)
    video_path = task_dir / "source.mp4"
    total_bytes = 0

    try:
        with video_path.open("wb") as target:
            while chunk := file.file.read(1024 * 1024):
                total_bytes += len(chunk)
                if total_bytes > settings.max_upload_bytes:
                    raise HTTPException(status_code=400, detail="视频超过上传大小限制")
                target.write(chunk)

        if total_bytes == 0:
            raise HTTPException(status_code=400, detail="上传的视频为空")

        metadata = {
            "team1": team1,
            "team2": team2,
            "score1": score1,
            "score2": score2,
            "frame_step": settings.video_frame_step,
        }
        task_repo.create_task(
            task_id=task_id,
            video_name=display_name,
            video_path=str(video_path.resolve()),
            metadata=metadata,
        )
        if settings.task_backend == "celery":
            try:
                from worker.celery_app import enqueue_video_task

                enqueue_video_task(task_id)
            except Exception as exc:
                task_repo.delete_task(task_id)
                raise HTTPException(
                    status_code=503,
                    detail="无法投递视频任务，请确认已安装 Celery Redis 依赖、Redis 已启动且 CELERY_BROKER_URL 正确",
                ) from exc
        start_preview_generation(task_dir)
    except Exception:
        shutil.rmtree(task_dir, ignore_errors=True)
        raise
    finally:
        file.file.close()

    return ApiEnvelope(
        result=TaskCreated(
            task_id=task_id,
            status="pending",
            frame_step=settings.video_frame_step,
        )
    )


@router.get("/{task_id}/preview/status", response_model=ApiEnvelope[TaskPreviewStatus])
def get_task_preview_status(task_id: str) -> ApiEnvelope[TaskPreviewStatus]:
    row = task_repo.get_task(task_id)
    if row is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    task_dir = Path(row["video_path"]).parent
    result = TaskPreviewStatus.model_validate(get_preview_state(task_dir))
    return ApiEnvelope(result=result)


@router.get("/{task_id}/preview")
def get_task_preview(task_id: str) -> FileResponse:
    row = task_repo.get_task(task_id)
    if row is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    preview_path = get_preview_file(Path(row["video_path"]).parent)
    if preview_path is None:
        raise HTTPException(status_code=409, detail="浏览器预览尚未准备完成")
    return FileResponse(
        preview_path,
        media_type="video/mp4",
        filename=f"{task_id}-preview.mp4",
        content_disposition_type="inline",
    )


@router.get("", response_model=ApiEnvelope[list[TaskListItem]])
def list_tasks(limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0)) -> ApiEnvelope[list[TaskListItem]]:
    items = [TaskListItem.model_validate(row) for row in task_repo.list_tasks(limit=limit, offset=offset)]
    return ApiEnvelope(result=items)


@router.get("/{task_id}", response_model=ApiEnvelope[TaskStatus])
def get_task(task_id: str) -> ApiEnvelope[TaskStatus]:
    row = task_repo.get_task(task_id)
    if row is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return ApiEnvelope(result=TaskStatus.model_validate(row))


@router.delete("/{task_id}", response_model=ApiEnvelope[dict[str, Any]])
def delete_finished_task(task_id: str) -> ApiEnvelope[dict[str, Any]]:
    row = task_repo.get_task(task_id)
    if row is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if row["status"] not in {"ready", "failed"}:
        raise HTTPException(status_code=409, detail="任务处理中，完成后才能删除")

    runs_dir = settings.runs_dir.resolve()
    task_dir = Path(row["video_path"]).resolve().parent
    try:
        task_dir.relative_to(runs_dir)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="任务文件目录无效，拒绝删除") from exc
    if task_dir == runs_dir:
        raise HTTPException(status_code=500, detail="任务文件目录无效，拒绝删除")

    result, _ = task_repo.delete_finished_task(task_id)
    if result == "not_found":
        raise HTTPException(status_code=404, detail="任务不存在")
    if result != "deleted":
        raise HTTPException(status_code=409, detail="任务处理中，完成后才能删除")

    remove_preview_task_data(task_dir)
    return ApiEnvelope(result={"task_id": task_id, "deleted": True})


@router.get("/{task_id}/detections", response_model=ApiEnvelope[list[dict[str, Any]]])
def get_detections(
    task_id: str,
    t_start: float = Query(default=0, ge=0),
    t_end: float | None = Query(default=None, ge=0),
) -> ApiEnvelope[list[dict[str, Any]]]:
    row = task_repo.get_task(task_id)
    if row is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if t_end is not None and t_end < t_start:
        raise HTTPException(status_code=400, detail="t_end 必须大于等于 t_start")
    rows = _load_jsonl(settings.runs_dir / task_id / "detections.jsonl", t_start=t_start, t_end=t_end)
    return ApiEnvelope(result=rows)


@router.get("/{task_id}/events", response_model=ApiEnvelope[list[EventItem]])
def get_events(task_id: str) -> ApiEnvelope[list[EventItem]]:
    row = task_repo.get_task(task_id)
    if row is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    events = [EventItem.model_validate(row) for row in _load_jsonl(settings.runs_dir / task_id / "events.jsonl")]
    return ApiEnvelope(result=events)


@router.get("/{task_id}/narration", response_model=ApiEnvelope[dict[str, Any]])
def get_narration(task_id: str) -> ApiEnvelope[dict[str, Any]]:
    row = task_repo.get_task(task_id)
    if row is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    path = settings.runs_dir / task_id / "narration.json"
    if not path.exists():
        return ApiEnvelope(result={"task_id": task_id, "status": "pending" if row["status"] != "ready" else "not_started", "text": "", "sections": []})
    return ApiEnvelope(result=json.loads(path.read_text(encoding="utf-8")))


@router.post("/{task_id}/narration/retry", response_model=ApiEnvelope[dict[str, Any]], status_code=202)
def retry_narration(task_id: str, background_tasks: BackgroundTasks) -> ApiEnvelope[dict[str, Any]]:
    row = task_repo.get_task(task_id)
    if row is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if row["status"] != "ready":
        raise HTTPException(status_code=409, detail="视频分析完成后才能生成解说")
    events_path = settings.runs_dir / task_id / "events.jsonl"
    if not events_path.exists():
        raise HTTPException(status_code=409, detail="事件数据尚未准备好")
    narration_path = events_path.parent / "narration.json"
    if narration_path.exists():
        existing = json.loads(narration_path.read_text(encoding="utf-8"))
        if existing.get("status") == "running":
            raise HTTPException(status_code=409, detail="解说正在生成中")
    from worker.narration_service import write_narration

    write_narration(narration_path, {"task_id": task_id, "status": "running", "text": "", "sections": []})
    task_repo.update_task_metadata(task_id, narration_status="running")
    background_tasks.add_task(_retry_narration_in_background, task_id, events_path)
    return ApiEnvelope(result={"task_id": task_id, "status": "running"})


def _retry_narration_in_background(task_id: str, events_path: Path) -> None:
    from worker.narration_service import run_task_narration

    result = run_task_narration(task_id, events_path)
    task_repo.update_task_metadata(task_id, narration_status=result["status"])

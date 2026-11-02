from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, File, Form, Request, UploadFile

from app.core.config import settings
from app.core.errors import InputError
from app.schemas.envelope import ApiEnvelope
from app.schemas.demos import ImageBatchCreated, ImageBatchStatus, ImageDetectionResult
from app.services.image_batch_store import batch_store
from app.services.image_inputs import check_image_bytes
from app.services.model_access import require_image_detector

router = APIRouter(tags=["detect"])


@router.post("/detect", summary="单张图像球员检测", response_model=ApiEnvelope[ImageDetectionResult])
def detect_image(
    request: Request,
    file: UploadFile = File(..., description="PNG/JPG，最大 10 MB"),
    conf: float = Form(0.25, ge=0.05, le=0.9),
    iou: float = Form(0.55, ge=0.3, le=0.95),
) -> ApiEnvelope[ImageDetectionResult]:
    data = check_image_bytes(
        file.filename or "",
        file.file.read(settings.max_image_upload_bytes + 1),
    )
    result = require_image_detector(request).api_detect(data, conf=conf, iou=iou)
    return ApiEnvelope(result=result)


@router.post(
    "/detect/batch",
    summary="批量图像检测，返回任务编号",
    response_model=ApiEnvelope[ImageBatchCreated],
)
def detect_batch(
    request: Request,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(..., description="PNG/JPG，最多 20 张"),
) -> ApiEnvelope[ImageBatchCreated]:
    detector = require_image_detector(request)
    if not 1 <= len(files) <= settings.max_batch_images:
        raise InputError(f"每次请上传 1 到 {settings.max_batch_images} 张图片")

    payloads: list[tuple[str, bytes]] = []
    for upload in files:
        data = check_image_bytes(
            upload.filename or "",
            upload.file.read(settings.max_image_upload_bytes + 1),
        )
        payloads.append((upload.filename or "image", data))

    task_id = batch_store.create(len(payloads))
    background_tasks.add_task(batch_store.run, detector, task_id, payloads)
    return ApiEnvelope(result={"task_id": task_id, "total": len(payloads), "backend": "background"})


@router.get(
    "/batch/{task_id}",
    summary="查询批量检测进度与结果",
    response_model=ApiEnvelope[ImageBatchStatus],
)
def get_batch(task_id: str) -> ApiEnvelope[ImageBatchStatus]:
    return ApiEnvelope(result=batch_store.get(task_id))

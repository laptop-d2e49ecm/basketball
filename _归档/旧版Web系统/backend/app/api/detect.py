"""图像检测 API：单张同步 + 批量异步（实验 3 INT8 模型服务化）。"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, File, Form, Request, UploadFile

from ..core.config import DEFAULT_CONF, DEFAULT_IOU, MAX_BATCH_IMAGES
from ..core.schemas import ok
from ..services import batch_store
from preprocess import check_image_bytes

router = APIRouter(tags=["detect"])


@router.post("/detect", summary="单张图像球员检测（实验3 INT8 模型）")
def detect_image(
    request: Request,
    file: UploadFile = File(..., description="PNG/JPG，≤10MB"),
    conf: float = Form(DEFAULT_CONF, ge=0.05, le=0.9, description="置信度阈值"),
    iou: float = Form(DEFAULT_IOU, ge=0.3, le=0.95, description="NMS IoU 阈值"),
):
    data = check_image_bytes(file.filename or "", file.file.read())
    result = request.app.state.detector.api_detect(data, conf=conf, iou=iou)
    return ok(result)


@router.post("/detect/batch", summary="批量检测（异步，返回 task_id）")
def detect_batch(
    request: Request,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(..., description=f"PNG/JPG，单次 ≤{MAX_BATCH_IMAGES} 张"),
):
    if not 1 <= len(files) <= MAX_BATCH_IMAGES:
        from ..core.errors import InputError
        raise InputError(f"批量检测单次 1-{MAX_BATCH_IMAGES} 张（收到 {len(files)}）")
    payloads = []
    for f in files:
        payloads.append((f.filename or "image", check_image_bytes(f.filename or "", f.file.read())))
    task_id = batch_store.create(len(payloads))
    background_tasks.add_task(batch_store.run_batch, request.app.state.detector,
                              task_id, payloads)
    return ok({"task_id": task_id, "total": len(payloads), "backend": "background"})


@router.get("/batch/{task_id}", summary="查询批量任务进度/结果")
def get_batch(task_id: str):
    return ok(batch_store.get(task_id))

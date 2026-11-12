"""统一响应包装与请求体模型。"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


def ok(result: Any = None, msg: str = "ok") -> dict:
    """统一成功响应：{"code": 0, "result": ..., "msg": "ok"}。"""
    return {"code": 0, "result": result, "msg": msg}


class TextInput(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000, description="待分类的解说文本")


class Box(BaseModel):
    cx: float = Field(..., ge=0, le=1, description="归一化中心 x ∈[0,1]")
    cy: float = Field(..., ge=0, le=1)
    w: float = Field(..., gt=0, le=1, description="归一化宽")
    h: float = Field(..., gt=0, le=1)
    conf: float = Field(..., ge=0, le=1)


class DetectResult(BaseModel):
    boxes: list[Box]
    player_count: int
    dropped_boxes: int
    image_w: int
    image_h: int
    conf_thr: float
    iou_thr: float
    infer_ms: float
    total_ms: float


class TopKItem(BaseModel):
    label: str
    prob: float


class TextResult(BaseModel):
    label: str
    confidence: float
    top3: list[TopKItem]
    chars: int
    infer_ms: float


class ImageSide(BaseModel):
    is_court: bool
    player_count: int
    avg_conf: float
    infer_ms: float


class TextSide(BaseModel):
    label: str
    is_basketball_text: bool
    confidence: float


class MatchResult(BaseModel):
    match: bool
    image_side: ImageSide
    text_side: TextSide
    evidence: list[str]
    total_ms: float


class TaskCreated(BaseModel):
    task_id: str
    total: int
    backend: str


class TaskItemResult(BaseModel):
    filename: str
    ok: bool
    player_count: Optional[int] = None
    error: Optional[str] = None


class TaskStatus(BaseModel):
    task_id: str
    status: str
    done: int
    total: int
    results: list[TaskItemResult]


# ---- 视频分析任务（SQLite 任务表对外视图）----

class VideoTask(BaseModel):
    task_id: str
    video_name: str
    status: str = Field(..., description="pending/running/ready/failed")
    stage: str = Field("", description="decoding/detecting/events/commentary/done")
    progress: float = 0.0
    frames_done: int = 0
    frames_total: int = 0
    avg_infer_ms: Optional[float] = None
    total_seconds: Optional[float] = None
    error: Optional[str] = None
    video_duration_s: Optional[float] = None
    home_team: Optional[str] = None
    away_team: Optional[str] = None


class FrameBox(BaseModel):
    track_id: int
    cx: float
    cy: float
    w: float
    h: float
    conf: float


class FrameDetections(BaseModel):
    frame_idx: int
    t_ms: float
    boxes: list[FrameBox]


class EventItem(BaseModel):
    t_ms: float
    type: str
    source: str = "heuristic"
    text: str


class ModelMeta(BaseModel):
    detector: dict
    text_clf: dict
    tracker: dict
    task_backend: str
    app_version: str

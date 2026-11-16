from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

TaskState = Literal["pending", "running", "ready", "failed"]
PreviewState = Literal["processing", "ready", "failed"]


class TaskCreated(BaseModel):
    task_id: str
    status: TaskState
    frame_step: int = Field(ge=1)


class TaskPreviewStatus(BaseModel):
    status: PreviewState
    converted: bool = False
    error: str | None = None


class TaskStatus(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    task_id: str
    video_name: str
    metadata: dict[str, Any]
    status: TaskState
    stage: str
    progress: float
    error: str | None = None
    created_at: datetime
    finished_at: datetime | None = None
    frames_total: int | None = None
    frames_done: int = 0
    avg_infer_ms: float | None = None
    total_seconds: float | None = None


class TaskListItem(BaseModel):
    task_id: str
    video_name: str
    status: TaskState
    stage: str
    progress: float
    created_at: datetime
    finished_at: datetime | None = None


class EventItem(BaseModel):
    t_ms: int
    type: str
    source: Literal["heuristic", "action_model"] = "heuristic"
    text: str
    player_count: int | None = None
    track_ids: list[int] = Field(default_factory=list)
    # 事件时刻关键帧的视觉描述（画面观察）；旧任务/无视觉时为空
    scene: str = ""
    # 动作识别事件（type=action / source=action_model）的载荷
    action: str | None = None
    action_zh: str | None = None
    conf: float | None = None
    track_id: int | None = None

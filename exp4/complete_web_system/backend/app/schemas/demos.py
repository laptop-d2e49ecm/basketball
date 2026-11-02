from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ImageDetectionBox(BaseModel):
    cx: float = Field(ge=0, le=1)
    cy: float = Field(ge=0, le=1)
    w: float = Field(gt=0, le=1)
    h: float = Field(gt=0, le=1)
    conf: float = Field(ge=0, le=1)


class ImageDetectionResult(BaseModel):
    boxes: list[ImageDetectionBox]
    player_count: int = Field(ge=0)
    dropped_boxes: int = Field(ge=0)
    image_w: int = Field(gt=0)
    image_h: int = Field(gt=0)
    conf_thr: float = Field(ge=0, le=1)
    iou_thr: float = Field(ge=0, le=1)
    infer_ms: float = Field(ge=0)
    total_ms: float = Field(ge=0)


class TextClassCandidate(BaseModel):
    label: str
    prob: float = Field(ge=0, le=1)


class TextClassificationResult(BaseModel):
    label: str
    is_basketball_text: bool
    confidence: float = Field(ge=0, le=1)
    top3: list[TextClassCandidate]
    chars: int = Field(ge=0)
    infer_ms: float = Field(ge=0)


class MatchImageEvidence(BaseModel):
    is_court: bool
    player_count: int = Field(ge=0)
    avg_conf: float = Field(ge=0, le=1)
    infer_ms: float = Field(ge=0)


class MatchTextEvidence(BaseModel):
    label: str
    is_basketball_text: bool
    confidence: float = Field(ge=0, le=1)


class ImageTextMatchResult(BaseModel):
    match: bool
    image_side: MatchImageEvidence
    text_side: MatchTextEvidence
    evidence: list[str]
    total_ms: float = Field(ge=0)


class ImageBatchCreated(BaseModel):
    task_id: str
    total: int = Field(ge=1)
    backend: Literal["background"]


class ImageBatchItem(BaseModel):
    filename: str
    ok: bool
    player_count: int | None = Field(default=None, ge=0)
    error: str | None = None


class ImageBatchStatus(BaseModel):
    task_id: str
    status: Literal["running", "done"]
    done: int = Field(ge=0)
    total: int = Field(ge=1)
    results: list[ImageBatchItem]

"""健康检查与模型信息。"""
from __future__ import annotations

import json

from fastapi import APIRouter, Request

from ..core.config import APP_VERSION, TEXT_META
from ..core.schemas import ok

router = APIRouter(tags=["health"])


@router.get("/health", summary="服务与模型加载状态")
def health(request: Request):
    return ok({
        "status": "ok",
        "app_version": APP_VERSION,
        "detector_loaded": getattr(request.app.state, "detector", None) is not None,
        "text_clf_loaded": getattr(request.app.state, "text_clf", None) is not None,
    })


@router.get("/meta/model", summary="模型信息（指标为实验 2/3 实测口径）")
def model_meta(request: Request):
    meta = {}
    if TEXT_META.exists():
        m = json.loads(TEXT_META.read_text(encoding="utf-8"))
        meta = {
            "corpus_size": m.get("corpus_size"),
            "accuracy": m.get("accuracy"),
            "macro_f1": m.get("macro_f1"),
            "label_distribution": m.get("label_distribution"),
            "trained_at": m.get("trained_at"),
        }
    return ok({
        "detector": {
            "file": "a2_int8_val346.onnx",
            "source": "实验3 INT8 静态量化（val346 校准，首选部署版本）",
            "params_m": 3.13, "size_mb": 3.6, "test_map50": 0.420, "nc": 1, "cls": ["player"],
        },
        "text_clf": {"file": "text_action_clf.joblib", **meta},
        "app_version": APP_VERSION,
    })

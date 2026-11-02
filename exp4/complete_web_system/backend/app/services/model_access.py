from __future__ import annotations

from fastapi import Request

from app.core.config import settings
from app.core.errors import ModelError


def require_image_detector(request: Request):
    detector = getattr(request.app.state, "image_detector", None)
    if detector is None:
        reason = getattr(request.app.state, "image_detector_error", None)
        raise ModelError(f"图像检测服务未就绪：{reason or '模型尚未加载'}")
    return detector


def require_text_classifier(request: Request):
    classifier = getattr(request.app.state, "text_classifier", None)
    if classifier is None:
        reason = getattr(request.app.state, "text_classifier_error", None)
        if reason and "模型文件缺失" in reason:
            try:
                model_name = settings.text_model_path.relative_to(settings.backend_dir).as_posix()
            except ValueError:
                model_name = settings.text_model_path.name
            raise ModelError(f"文本分类模型未加载（{model_name} 缺失）")
        raise ModelError(f"文本分类模型未加载：{reason or '模型尚未加载'}")
    return classifier

"""图文匹配 API（任务书 4.2.3 多模型协同工作流：检测 → 文本分类 → 一致性判定）。"""
from __future__ import annotations

from fastapi import APIRouter, File, Form, Request, UploadFile

from ..core.errors import ModelError
from ..core.schemas import ok
from ..services.workflow import run_match
from preprocess import check_image_bytes, check_text

router = APIRouter(tags=["match"])


@router.post("/match", summary="图文匹配（图像检测 + 文本分类 工作流）")
def match_image_text(
    request: Request,
    file: UploadFile = File(..., description="PNG/JPG，≤10MB"),
    text: str = Form(..., description="待匹配的解说文本"),
    conf: float = Form(0.25, ge=0.05, le=0.9),
):
    clf = getattr(request.app.state, "text_clf", None)
    if clf is None:
        raise ModelError("文本分类模型未加载（app/ml/text_action_clf.joblib 缺失）")
    data = check_image_bytes(file.filename or "", file.file.read())
    text = check_text(text)
    result = run_match(request.app.state.detector, clf, data, text, conf=conf)
    return ok(result)

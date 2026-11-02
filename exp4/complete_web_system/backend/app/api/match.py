from __future__ import annotations

from fastapi import APIRouter, File, Form, Request, UploadFile

from app.core.config import settings
from app.core.errors import InputError
from app.schemas.demos import ImageTextMatchResult
from app.schemas.envelope import ApiEnvelope
from app.services.image_inputs import check_image_bytes, check_text
from app.services.match_workflow import run_match
from app.services.model_access import require_image_detector, require_text_classifier

router = APIRouter(tags=["match"])


@router.post(
    "/match",
    summary="图像检测与解说文本匹配",
    response_model=ApiEnvelope[ImageTextMatchResult],
)
def match_image_text(
    request: Request,
    file: UploadFile = File(..., description="PNG/JPG，最大 10 MB"),
    text: str = Form(..., description="待匹配的解说文本"),
    conf: float = Form(0.25, ge=0.05, le=0.9),
) -> ApiEnvelope[ImageTextMatchResult]:
    image = check_image_bytes(
        file.filename or "",
        file.file.read(settings.max_image_upload_bytes + 1),
    )
    clean_text = check_text(text)
    if not clean_text:
        raise InputError("文本不能为空")
    detector = require_image_detector(request)
    text_classifier = require_text_classifier(request)
    return ApiEnvelope(result=run_match(detector, text_classifier, image, clean_text, conf=conf))

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.core.errors import InputError
from app.schemas.demos import TextClassificationResult
from app.schemas.envelope import ApiEnvelope
from app.services.image_inputs import check_text
from app.services.model_access import require_text_classifier

router = APIRouter(tags=["text"])


class TextClassifyRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000, description="待分类的篮球解说文本")


@router.post(
    "/text/classify",
    summary="解说文本动作分类",
    response_model=ApiEnvelope[TextClassificationResult],
)
def classify_text(request: Request, body: TextClassifyRequest) -> ApiEnvelope[TextClassificationResult]:
    text = check_text(body.text)
    if not text:
        raise InputError("文本不能为空")
    return ApiEnvelope(result=require_text_classifier(request).predict(text))

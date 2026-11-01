"""解说文本动作分类 API（实验 1 语料弱监督模型）。"""
from __future__ import annotations

from fastapi import APIRouter, Request

from ..core.schemas import TextInput, ok

router = APIRouter(tags=["text"])


@router.post("/text/classify", summary="解说文本动作分类")
def classify_text(request: Request, body: TextInput):
    return ok(request.app.state.text_clf.predict(body.text))

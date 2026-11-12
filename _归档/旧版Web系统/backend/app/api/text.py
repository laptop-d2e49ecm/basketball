"""解说文本动作分类 API（实验 1 语料弱监督模型）。"""
from __future__ import annotations

from fastapi import APIRouter, Request

from ..core.errors import ModelError
from ..core.schemas import TextInput, ok

router = APIRouter(tags=["text"])


@router.post("/text/classify", summary="解说文本动作分类")
def classify_text(request: Request, body: TextInput):
    clf = getattr(request.app.state, "text_clf", None)
    if clf is None:
        raise ModelError("文本分类模型未加载（app/ml/text_action_clf.joblib 缺失）")
    return ok(clf.predict(body.text))

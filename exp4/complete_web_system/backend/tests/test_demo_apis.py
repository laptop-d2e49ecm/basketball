from __future__ import annotations

import asyncio
import io
from typing import Any

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.api.detect import router as detect_router
from app.api.match import router as match_router
from app.api.text import router as text_router
from app.core.errors import register_exception_handlers


class FakeDetector:
    def api_detect(self, _data: bytes, conf: float = 0.25, iou: float = 0.55) -> dict:
        return {
            "boxes": [{"cx": 0.5, "cy": 0.5, "w": 0.3, "h": 0.6, "conf": 0.91}],
            "player_count": 1,
            "dropped_boxes": 0,
            "image_w": 64,
            "image_h": 64,
            "conf_thr": conf,
            "iou_thr": iou,
            "infer_ms": 4.2,
            "total_ms": 5.0,
        }


class FakeTextClassifier:
    def predict(self, _text: str) -> dict:
        return {
            "label": "投篮",
            "is_basketball_text": True,
            "confidence": 0.95,
            "top3": [{"label": "投篮", "prob": 0.95}],
            "chars": 8,
            "infer_ms": 0.6,
        }


def _png_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (64, 64), color="white").save(output, format="PNG")
    return output.getvalue()


def _app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.state.image_detector = FakeDetector()
    app.state.text_classifier = FakeTextClassifier()
    app.include_router(detect_router, prefix="/api/v1")
    app.include_router(text_router, prefix="/api/v1")
    app.include_router(match_router, prefix="/api/v1")
    return app


def _request(app: FastAPI, method: str, url: str, **kwargs: Any):
    async def send():
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            return await client.request(method, url, **kwargs)

    return asyncio.run(send())


def test_detect_endpoint_returns_api_envelope_and_normalized_boxes():
    response = _request(
        _app(),
        "POST",
        "/api/v1/detect",
        files={"file": ("game.png", _png_bytes(), "image/png")},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 0
    assert payload["result"]["player_count"] == 1
    assert payload["result"]["boxes"][0]["cx"] == 0.5


def test_text_endpoint_rejects_blank_commentary():
    response = _request(_app(), "POST", "/api/v1/text/classify", json={"text": "   "})
    assert response.status_code == 400
    assert response.json()["code"] == 400


def test_match_endpoint_combines_image_and_commentary_results():
    response = _request(
        _app(),
        "POST",
        "/api/v1/match",
        data={"text": "底角三分出手命中"},
        files={"file": ("game.png", _png_bytes(), "image/png")},
    )
    assert response.status_code == 200
    result = response.json()["result"]
    assert result["match"] is True
    assert result["image_side"]["player_count"] == 1
    assert result["text_side"]["label"] == "投篮"


def test_detect_endpoint_rejects_corrupt_image():
    response = _request(
        _app(),
        "POST",
        "/api/v1/detect",
        files={"file": ("broken.png", b"not an image", "image/png")},
    )
    assert response.status_code == 400
    assert response.json()["code"] == 400

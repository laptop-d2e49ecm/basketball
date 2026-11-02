from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.detect import router as detect_router
from app.api.match import router as match_router
from app.api.tasks import router as tasks_router
from app.api.text import router as text_router
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.db.database import initialize_database
from app.db import task_repo
from app.schemas.envelope import ApiEnvelope
from app.ws.task_ws import router as task_ws_router

logger = logging.getLogger(__name__)


def _load_optional_model(
    app: FastAPI,
    state_name: str,
    error_name: str,
    path: Path,
    service_name: str,
) -> None:
    setattr(app.state, state_name, None)
    if not path.is_file():
        setattr(app.state, error_name, f"模型文件缺失：{path.name}")
        logger.warning("%s model is unavailable: %s", service_name, path)
        return

    try:
        if state_name == "image_detector":
            from app.services.image_detector import ImageDetector

            model = ImageDetector(path)
        else:
            from app.services.text_classifier import TextClassifier

            model = TextClassifier(path, settings.text_meta_path)
        setattr(app.state, state_name, model)
        setattr(app.state, error_name, None)
        logger.info("Loaded %s model from %s", service_name, path)
    except Exception as exc:  # Optional demo models must not stop the video API.
        setattr(app.state, error_name, f"{type(exc).__name__}: {exc}")
        logger.exception("Unable to load %s model", service_name)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.runs_dir.mkdir(parents=True, exist_ok=True)
    initialize_database()
    _load_optional_model(app, "image_detector", "image_detector_error", settings.image_model_path, "image detector")
    _load_optional_model(app, "text_classifier", "text_classifier_error", settings.text_model_path, "text classifier")
    yield
    app.state.image_detector = None
    app.state.text_classifier = None


app = FastAPI(title="篮球 AI 赛事解说员 API", version="0.2.0", lifespan=lifespan)
register_exception_handlers(app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(tasks_router)
app.include_router(detect_router, prefix="/api/v1")
app.include_router(text_router, prefix="/api/v1")
app.include_router(match_router, prefix="/api/v1")
app.include_router(task_ws_router)


@app.get("/api/v1/meta/model", response_model=ApiEnvelope[dict[str, object]])
def model_info() -> ApiEnvelope[dict[str, object]]:
    text_meta = {}
    if settings.text_meta_path.is_file():
        try:
            text_meta = json.loads(settings.text_meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("Unable to read text classifier metadata: %s", settings.text_meta_path)
    return ApiEnvelope(result={
        "name": "YOLOv8n",
        "parameters": "3.2M",
        "map50": 0.418,
        "classes": ["player"],
        "weights_available": settings.model_path.is_file(),
        "avg_infer_ms": task_repo.measured_average_infer_ms(),
        "image_detector": {
            "file": settings.image_model_path.name,
            "weights_available": settings.image_model_path.is_file(),
            "loaded": getattr(app.state, "image_detector", None) is not None,
            "test_map50": 0.420,
            "runtime": "ONNX Runtime CPU",
        },
        "text_classifier": {
            "file": settings.text_model_path.name,
            "weights_available": settings.text_model_path.is_file(),
            "loaded": getattr(app.state, "text_classifier", None) is not None,
            "accuracy": text_meta.get("accuracy"),
            "macro_f1": text_meta.get("macro_f1"),
            "corpus_size": text_meta.get("corpus_size"),
        },
    })


@app.get("/api/v1/health", response_model=ApiEnvelope[dict[str, object]])
def health() -> ApiEnvelope[dict[str, object]]:
    image_detector_loaded = getattr(app.state, "image_detector", None) is not None
    text_classifier_loaded = getattr(app.state, "text_classifier", None) is not None
    return ApiEnvelope(result={
        "status": "ok",
        "detector_loaded": image_detector_loaded,
        "text_clf_loaded": text_classifier_loaded,
        "backend_mode": settings.task_backend,
        "version": app.version,
        "video_frame_step": settings.video_frame_step,
        # Keep descriptive aliases for the existing project UI and scripts.
        "image_detector_loaded": image_detector_loaded,
        "text_classifier_loaded": text_classifier_loaded,
    })

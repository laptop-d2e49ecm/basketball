from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BACKEND_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    backend_dir: Path = BACKEND_DIR
    database_path: Path = Path(os.getenv("BASKETBALL_DB_PATH", str(BACKEND_DIR / "tasks.db")))
    runs_dir: Path = Path(os.getenv("BASKETBALL_RUNS_DIR", str(BACKEND_DIR / "runs")))
    model_path: Path = Path(os.getenv("BASKETBALL_MODEL_PATH", str(BACKEND_DIR / "weights" / "best.pt")))
    image_model_path: Path = Path(
        os.getenv("BASKETBALL_IMAGE_MODEL_PATH", str(BACKEND_DIR / "weights" / "a2_int8_val346.onnx"))
    )
    text_model_path: Path = Path(
        os.getenv("BASKETBALL_TEXT_MODEL_PATH", str(BACKEND_DIR / "app" / "ml" / "text_action_clf.joblib"))
    )
    text_meta_path: Path = Path(
        os.getenv("BASKETBALL_TEXT_META_PATH", str(BACKEND_DIR / "app" / "ml" / "text_clf_meta.json"))
    )
    max_upload_bytes: int = int(os.getenv("BASKETBALL_MAX_UPLOAD_BYTES", str(5 * 1024 * 1024 * 1024)))
    max_image_upload_bytes: int = int(os.getenv("BASKETBALL_MAX_IMAGE_UPLOAD_BYTES", str(10 * 1024 * 1024)))
    max_batch_images: int = int(os.getenv("BASKETBALL_MAX_BATCH_IMAGES", "20"))
    worker_poll_seconds: float = float(os.getenv("BASKETBALL_WORKER_POLL_SECONDS", "1"))
    image_size: int = int(os.getenv("BASKETBALL_IMAGE_SIZE", "640"))
    video_frame_step: int = max(1, int(os.getenv("BASKETBALL_FRAME_STEP", "2")))
    inference_device: str = os.getenv("BASKETBALL_DEVICE", "auto")
    task_backend: str = os.getenv("TASK_BACKEND", "worker").strip().lower()
    celery_broker_url: str = os.getenv("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")

    def __post_init__(self) -> None:
        if self.task_backend not in {"worker", "celery"}:
            raise ValueError("TASK_BACKEND must be either 'worker' or 'celery'")


settings = Settings()

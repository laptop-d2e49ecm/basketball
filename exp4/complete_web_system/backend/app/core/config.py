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
        os.getenv("BASKETBALL_IMAGE_MODEL_PATH", str(BACKEND_DIR / "weights" / "a2v2_int8_val173.onnx"))
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
    # 动作识别（实验5 视觉动作线）：on 时检测后按 track 滑窗识别 14 类动作事件；
    # 权重缺失或推理失败自动回退启发式事件，不影响任务完成。
    # 部署用 FP32 ONNX（INT8 动态量化在 3D 卷积上慢约 28 倍，见 scripts/06_action 评估）
    action_recognition_enabled: bool = (
        os.getenv("BASKETBALL_ACTION", "on").strip().lower() in {"1", "on", "true", "yes"}
    )
    action_model_path: Path = Path(
        os.getenv(
            "BASKETBALL_ACTION_MODEL_PATH",
            str(BACKEND_DIR / "weights" / "action_mc3_18.onnx"),
        )
    )
    action_meta_path: Path = Path(
        os.getenv(
            "BASKETBALL_ACTION_META_PATH",
            str(BACKEND_DIR / "weights" / "action_clf_meta.json"),
        )
    )
    action_conf_threshold: float = float(os.getenv("BASKETBALL_ACTION_CONF", "0.6"))
    action_cooldown_ms: int = int(os.getenv("BASKETBALL_ACTION_COOLDOWN_MS", "3000"))
    task_backend: str = os.getenv("TASK_BACKEND", "worker").strip().lower()
    celery_broker_url: str = os.getenv("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
    # 视频事件解说实现：stub=模板句（默认，无需 key），llm=大模型生成
    commentary_backend: str = os.getenv("BASKETBALL_COMMENTARY", "stub").strip().lower()
    # 单任务最多调用几次大模型生成解说（超出的走模板句）
    commentary_max_calls: int = int(os.getenv("BASKETBALL_COMMENTARY_MAX_CALLS", "12"))
    # 视频解说画面观察：on 时抓事件时刻关键帧交视觉大模型描述，作为解说的第二事实源
    vision_caption_enabled: bool = os.getenv("BASKETBALL_VISION_CAPTIONS", "on").strip().lower() in {"1", "on", "true", "yes"}
    # 单任务最多抓帧调视觉模型的次数（超出不注入画面观察）
    vision_max_calls: int = int(os.getenv("BASKETBALL_VISION_MAX_CALLS", "16"))
    # 解说批量生成：一次 LLM 调用产出 N 条事件解说（配额消耗降为 1/N）；1=退回逐条
    commentary_batch_size: int = max(1, int(os.getenv("BASKETBALL_COMMENTARY_BATCH", "5")))

    def __post_init__(self) -> None:
        if self.task_backend not in {"worker", "celery"}:
            raise ValueError("TASK_BACKEND must be either 'worker' or 'celery'")
        if self.commentary_backend not in {"stub", "llm"}:
            raise ValueError("BASKETBALL_COMMENTARY must be either 'stub' or 'llm'")


settings = Settings()

"""应用配置：路径、限制、默认阈值、跨域与异步任务后端选择（.env/环境变量可覆盖）。"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent          # exp4/backend/
ML_DIR = BASE_DIR / "app" / "ml"
WEIGHTS_DIR = BASE_DIR / "weights"
RUNS_DIR = Path(os.environ.get("EXP4_RUNS_DIR", BASE_DIR / "runs"))
RUNS_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = Path(os.environ.get("EXP4_DB", BASE_DIR / "tasks.db"))

API_V1 = "/api/v1"
APP_VERSION = "1.0.0-exp4"

# ---- 模型文件 ----
# 图像检测：实验 3 首选部署版本（INT8 静态量化，3.6MB，test mAP50=0.420）
DETECTOR_MODEL = WEIGHTS_DIR / "a2_int8_val346.onnx"
# 视频跟踪：实验 2 部署选型（track 模式依赖 ultralytics 内置 ByteTrack）
TRACKER_MODEL = WEIGHTS_DIR / "best.pt"
# 文本分类：实验 1 解说语料弱监督训练（train_text_clf.py 产出）
TEXT_MODEL = ML_DIR / "text_action_clf.joblib"
TEXT_META = ML_DIR / "text_clf_meta.json"

# ---- 输入限制（对齐实验 1 图像校验规则）----
MAX_UPLOAD_MB = 10
MAX_VIDEO_MB = 200
ALLOWED_IMAGE_EXTS = {".png", ".jpg", ".jpeg"}
ALLOWED_VIDEO_EXTS = {".mp4", ".mov", ".avi"}
MAX_BATCH_IMAGES = 20
MAX_TEXT_CHARS = 2000

# ---- 检测默认参数（letterbox 与后处理口径同实验 3 infer.py）----
DEFAULT_CONF = 0.25
DEFAULT_IOU = 0.55
MIN_BOX_SIDE_PX = 8          # 实验 1 增强规则沿用：出画/过小框丢弃并计数
DOMAIN_CONF_THR = 0.25       # 文本分类器低于该置信度判为"非篮球赛事文本"

# ---- 视频流水线 ----
FRAME_STEP = int(os.environ.get("EXP4_FRAME_STEP", "1"))   # 逐帧起步，基线实测后再决策
TRACK_CONF = 0.3
VIDEO_IMGSZ = 640

# ---- 跨域：开发环境允许 Vite 默认端口（生产改为实际域名）----
CORS_ORIGINS = os.environ.get(
    "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
).split(",")

# ---- 异步任务后端：worker（默认，SQLite 轮询，零外部依赖）/ celery（需 Redis）----
TASK_BACKEND = os.environ.get("TASK_BACKEND", "worker")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# ---- 静态托管（课程演示：前端 build 产物由 API 进程直接托管）----
STATIC_DIR = Path(os.environ.get("EXP4_STATIC_DIR", BASE_DIR / "static"))

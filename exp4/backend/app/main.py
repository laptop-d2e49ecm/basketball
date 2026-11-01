"""实验 4 本侧 FastAPI 入口（检测/文本/匹配 三 API）。

队友的视频主线（tasks/WS/Worker）合并时：将本文件的 include_routers 与
lifespan 模型加载并入她的 main.py 即可，路由文件零改动。
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import detect, health, match, text
from app.core.config import API_V1, CORS_ORIGINS, DETECTOR_MODEL, STATIC_DIR, TEXT_MODEL
from app.core.errors import register_exception_handlers
from app.services.detector import Detector
from app.services.text_clf import TextClassifier


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.detector = Detector(DETECTOR_MODEL)        # 实验3 INT8 模型，启动加载一次
    try:
        app.state.text_clf = TextClassifier(TEXT_MODEL)  # 实验1 语料训练的文本分类器
    except Exception:  # noqa: BLE001 —— 缺模型不阻断视频主线服务启动，health 如实上报
        import logging
        logging.getLogger("uvicorn.error").warning(
            "文本分类模型未加载：app/ml/text_action_clf.joblib 缺失，"
            "/text/classify 与 /match 将返回 500（视频任务线不受影响）")
        app.state.text_clf = None
    yield
    app.state.detector = None
    app.state.text_clf = None


app = FastAPI(
    title="basketball-ai exp4 本侧服务",
    description="球员检测（实验3 INT8 模型）/ 解说文本分类 / 图文匹配 —— 统一信封 {code,result,msg}",
    version="1.0.0-exp4",
    lifespan=lifespan,
)

register_exception_handlers(app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,       # 开发环境 localhost:5173，生产改为实际域名
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (health.router, detect.router, text.router, match.router):
    app.include_router(r, prefix=API_V1)

if STATIC_DIR.exists():               # 课程演示：托管前端 build 产物（可选）
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)

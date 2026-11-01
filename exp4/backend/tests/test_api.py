"""实验 4 本侧 API 契约测试。

覆盖：坐标往返（实验 1 教训防线）、统一信封、三 API 正常路径、
异常路径（400 参数错 / 404 资源错）、批量异步任务状态流转。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
REPO = BACKEND.parent.parent

from app.core.coords import assert_valid_norm_boxes, norm_to_xyxy_px, xyxy_px_to_norm  # noqa: E402
from app.main import app  # noqa: E402

SAMPLE_IMG = REPO / "share_exp4_handoff" / "samples" / "images" / "v_-6Os86HzwCs_c001__f000025.jpg"
if not SAMPLE_IMG.exists():  # 兜底：直接从实验 1 test 划分取
    SAMPLE_IMG = REPO / "data" / "splits" / "yolo" / "images" / "test" / "v_-6Os86HzwCs_c001__f000025.jpg"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:   # 进入时触发 lifespan（加载 ONNX 与文本模型）
        yield c


# ---- 坐标契约（实验 1 增强教训的制度化防线）----

def test_coords_roundtrip():
    xy = np.array([[100, 50, 300, 400], [10, 10, 630, 470]], dtype=np.float32)
    n = xyxy_px_to_norm(xy, 640, 480)
    assert_valid_norm_boxes(n)                       # ∈[0,1] 且 w,h>0
    back = norm_to_xyxy_px(n, 640, 480)
    assert np.abs(back - xy).max() < 1e-3            # 往返误差 <1e-3（float32 像素精度）


def test_coords_reject_collapsed_box():
    with pytest.raises(ValueError):
        assert_valid_norm_boxes(np.array([[0.5, 0.5, 0.0, 0.2]], dtype=np.float32))  # 压成一点
    with pytest.raises(ValueError):
        assert_valid_norm_boxes(np.array([[1.2, 0.5, 0.1, 0.2]], dtype=np.float32))  # 越界


# ---- 信封与健康检查 ----

def test_health_envelope(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0 and body["msg"] == "ok"
    assert body["result"]["detector_loaded"] and body["result"]["text_clf_loaded"]


def test_404_envelope(client):
    r = client.get("/api/v1/no/such/route")
    assert r.status_code == 404
    assert r.json()["code"] == 404


# ---- 检测 API ----

def test_detect_ok(client):
    r = client.post("/api/v1/detect", files={"file": ("t.jpg", SAMPLE_IMG.read_bytes(), "image/jpeg")})
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0
    res = body["result"]
    assert res["player_count"] >= 1 and res["dropped_boxes"] == 0
    assert res["infer_ms"] < 2000                    # 任务书合格线：前端展示 ≤2s
    for b in res["boxes"]:
        assert all(0 <= b[k] <= 1 for k in ("cx", "cy", "w", "h")) and b["w"] > 0 and b["h"] > 0


@pytest.mark.parametrize("name,data,code", [
    ("bad.txt", b"not an image", 400),               # 扩展名白名单
    ("bad.png", b"\x89PNG corrupt", 400),            # 损坏检测（实验 1 规则）
])
def test_detect_input_errors(client, name, data, code):
    r = client.post("/api/v1/detect", files={"file": (name, data, "application/octet-stream")})
    assert r.status_code == code
    assert r.json()["code"] == code and r.json()["result"] is None and r.json()["msg"]


# ---- 文本分类 API ----

def test_text_classify_basketball(client):
    r = client.post("/api/v1/text/classify", json={"text": "詹姆斯外线三分出手命中！"})
    assert r.json()["code"] == 0
    res = r.json()["result"]
    assert res["is_basketball_text"] and res["label"] in ("投篮", "比分局势")
    assert len(res["top3"]) == 3


def test_text_classify_ood(client):
    r = client.post("/api/v1/text/classify", json={"text": "今天天气晴朗适合出游"})
    res = r.json()["result"]
    assert res["is_basketball_text"] is False and res["label"] == "非篮球赛事文本"


def test_text_empty_400(client):
    r = client.post("/api/v1/text/classify", json={"text": ""})
    assert r.status_code == 400 and r.json()["code"] == 400   # RequestValidationError→400


# ---- 图文匹配 API（工作流） ----

def test_match_positive(client):
    r = client.post("/api/v1/match", data={"text": "精彩的突破上篮打进！"},
                    files={"file": ("t.jpg", SAMPLE_IMG.read_bytes(), "image/jpeg")})
    res = r.json()["result"]
    assert res["match"] is True
    assert res["image_side"]["is_court"] and res["text_side"]["is_basketball_text"]
    assert len(res["evidence"]) == 2


def test_match_negative_by_text(client):
    r = client.post("/api/v1/match", data={"text": "股市今日大幅上涨"},
                    files={"file": ("t.jpg", SAMPLE_IMG.read_bytes(), "image/jpeg")})
    res = r.json()["result"]
    assert res["match"] is False and not res["text_side"]["is_basketball_text"]


# ---- 批量异步任务 ----

def test_batch_flow(client):
    img = SAMPLE_IMG.read_bytes()
    files = [("files", (f"{i}.jpg", img, "image/jpeg")) for i in range(3)]
    r = client.post("/api/v1/detect/batch", files=files)
    assert r.json()["code"] == 0
    task_id = r.json()["result"]["task_id"]
    for _ in range(60):                              # 轮询至完成（≤60s）
        st = client.get(f"/api/v1/batch/{task_id}").json()["result"]
        if st["status"] == "done":
            break
        time.sleep(0.5)
    assert st["status"] == "done" and st["done"] == st["total"] == 3
    assert all(x["ok"] and x["player_count"] >= 1 for x in st["results"])


def test_batch_unknown_404(client):
    r = client.get("/api/v1/batch/nonexistent")
    assert r.status_code == 404 and r.json()["code"] == 404

"""实验 4 本侧性能实测：真实 HTTP 服务上的端到端耗时（任务书合格线 ≤2s）。

用法：先启动服务（uvicorn app.main:app --port 8000），再运行本脚本。
产出：exp4/bench_results.json（avg/p50/p95，客户端往返口径 + 服务端分段耗时）。
"""
from __future__ import annotations

import json
import platform
import statistics
import time
from datetime import datetime
from pathlib import Path

import requests

BASE = "http://127.0.0.1:8000/api/v1"
SAMPLE = (Path(__file__).resolve().parents[2] / "share_exp4_handoff" / "samples" / "images"
          / "v_-6Os86HzwCs_c001__f000025.jpg")


def pct(vals: list[float], p: float) -> float:
    s = sorted(vals)
    return s[min(int(len(s) * p), len(s) - 1)]


def stats(vals: list[float]) -> dict:
    return {"n": len(vals), "avg_ms": round(statistics.mean(vals), 1),
            "p50_ms": round(pct(vals, 0.5), 1), "p95_ms": round(pct(vals, 0.95), 1),
            "min_ms": round(min(vals), 1), "max_ms": round(max(vals), 1)}


def bench_detect(n=10):
    img = SAMPLE.read_bytes()
    requests.get(f"{BASE}/health").raise_for_status()      # 预热连接
    requests.post(f"{BASE}/detect", files={"file": ("w.jpg", img, "image/jpeg")})  # 预热推理
    e2e, infer = [], []
    for _ in range(n):
        t0 = time.perf_counter()
        r = requests.post(f"{BASE}/detect", files={"file": ("t.jpg", img, "image/jpeg")})
        e2e.append((time.perf_counter() - t0) * 1000)
        res = r.json()["result"]
        infer.append(res["infer_ms"])
        assert r.json()["code"] == 0
    return {"client_e2e": stats(e2e), "server_infer": stats(infer),
            "player_count_last": res["player_count"], "image_kb": round(len(img) / 1024, 1)}


def bench_text(n=10):
    texts = ["詹姆斯外线三分出手命中！", "这球防守犯规了，裁判回看录像", "教练请求暂停调整战术"]
    requests.post(f"{BASE}/text/classify", json={"text": texts[0]})
    e2e = []
    labels = []
    for i in range(n):
        t = texts[i % len(texts)]
        t0 = time.perf_counter()
        r = requests.post(f"{BASE}/text/classify", json={"text": t})
        e2e.append((time.perf_counter() - t0) * 1000)
        assert r.json()["code"] == 0
        labels.append(r.json()["result"]["label"])
    return {"client_e2e": stats(e2e), "labels_seen": sorted(set(labels))}


def bench_match(n=5):
    img = SAMPLE.read_bytes()
    e2e, server = [], []
    for _ in range(n):
        t0 = time.perf_counter()
        r = requests.post(f"{BASE}/match", data={"text": "精彩的突破上篮打进！"},
                          files={"file": ("t.jpg", img, "image/jpeg")})
        e2e.append((time.perf_counter() - t0) * 1000)
        assert r.json()["code"] == 0
        server.append(r.json()["result"]["total_ms"])
    return {"client_e2e": stats(e2e), "server_total": stats(server)}


if __name__ == "__main__":
    out = {
        "bench_at": datetime.now().isoformat(timespec="seconds"),
        "machine": platform.platform() + f" / {platform.processor()}",
        "spec": "任务书合格线：前端展示延迟 ≤2000ms（本表 client_e2e 为同机 HTTP 往返口径）",
        "detect": bench_detect(),
        "text": bench_text(),
        "match": bench_match(),
    }
    dst = Path(__file__).resolve().parent.parent / "bench_results.json"
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    print("saved ->", dst)

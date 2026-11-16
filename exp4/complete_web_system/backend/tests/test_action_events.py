# -*- coding: utf-8 -*-
"""动作识别事件流的最小单元测试：阈值、背景类、冷却与窗口最少帧数。

识别器与帧解码均注入桩（不依赖 onnx 权重与视频文件）。
"""
from __future__ import annotations

import json

import numpy as np

from worker.action_service import ActionRecognizer, iter_action_events


class FakeRecognizer(ActionRecognizer):
    """按脚本逐次返回 (label, prob) 的识别器桩。"""

    def __init__(self, scripted: list[tuple[str, float]]):
        # 不走父类构造（避免 Path(None)）；只补齐 iter_action_events 用到的属性
        self.scripted = scripted
        self.calls: list[int] = []
        self.classes = ["dribble", "pass", "sag", "_none"]
        self.zh_names = {"dribble": "运球", "pass": "传球", "sag": "收缩防守", "_none": "无动作"}
        self.background_class = "_none"

    def classify(self, frames):  # noqa: D102 - 桩
        self.calls.append(len(frames))
        return self.scripted.pop(0)


def _loader(frame_idxs):
    return [np.zeros((720, 1280, 3), dtype=np.uint8) for _ in frame_idxs]


def _write_detections(path, tracks):
    """tracks: {track_id: [t_ms,...]}，每 200ms 一个观测，帧号随时间递增。"""
    rows = {}
    for tid, times in tracks.items():
        for t_ms in times:
            frame_idx = int(t_ms * 25 / 1000)
            row = rows.setdefault(frame_idx, {"frame_idx": frame_idx, "t_ms": t_ms,
                                              "image_w": 1280, "image_h": 720, "boxes": []})
            row["boxes"].append({"cx": 0.5, "cy": 0.5, "w": 0.1, "h": 0.2,
                                 "conf": 0.9, "track_id": tid})
    with path.open("w", encoding="utf-8") as f:
        for frame_idx in sorted(rows):
            f.write(json.dumps(rows[frame_idx]) + "\n")


def test_action_events_threshold_background_cooldown(tmp_path):
    detections = tmp_path / "detections.jsonl"
    _write_detections(detections, {
        1: list(range(0, 5200, 200)),    # 26 个观测：5 个完整窗口
        2: list(range(1000, 4200, 200)),  # 16 个观测：3 个窗口
    })
    scripted = [
        ("dribble", 0.90),  # t1 中心 500ms → 产出
        ("dribble", 0.95),  # t1 中心 1500ms → 同动作冷却期内，抑制
        ("pass", 0.85),     # t1 中心 2500ms → 不同动作，产出
        ("_none", 0.99),    # t1 中心 3500ms → 背景类，永不产出
        ("dribble", 0.50),  # t1 中心 4500ms → 低于阈值，抑制
        ("sag", 0.90),      # t2 中心 1500ms → 产出
        ("sag", 0.90),      # t2 中心 2500ms → 冷却抑制
        ("sag", 0.90),      # t2 中心 3500ms → 冷却抑制
    ]
    recognizer = FakeRecognizer(scripted)
    events = list(iter_action_events(detections, _loader, recognizer))

    emitted = [(e["track_id"], e["action"], e["t_ms"]) for e in events]
    assert emitted == [(1, "dribble", 500), (1, "pass", 2500), (2, "sag", 1500)]
    first = events[0]
    assert first["type"] == "action" and first["source"] == "action_model"
    assert first["action_zh"] == "运球" and 0.89 < first["conf"] <= 0.9
    assert recognizer.calls  # 全部窗口都真正调用了识别器
    assert not scripted  # 脚本恰好耗尽


def test_action_events_skip_short_windows(tmp_path):
    detections = tmp_path / "detections.jsonl"
    # 只有 3 个观测（< MIN_WINDOW_FRAMES=5），窗口应被跳过，不调用识别器
    _write_detections(detections, {7: [0, 200, 400]})
    recognizer = FakeRecognizer([])
    events = list(iter_action_events(detections, _loader, recognizer))
    assert events == []
    assert recognizer.calls == []


def test_action_events_no_tracks(tmp_path):
    detections = tmp_path / "detections.jsonl"
    _write_detections(detections, {1: list(range(0, 1000, 200))})
    # 全部观测去掉 track_id → 不产生窗口也不崩
    text = detections.read_text(encoding="utf-8").replace('"track_id": 1', '"track_id": null')
    detections.write_text(text, encoding="utf-8")
    recognizer = FakeRecognizer([])
    assert list(iter_action_events(detections, _loader, recognizer)) == []
    assert recognizer.calls == []

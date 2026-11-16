from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any, Iterator

import cv2
import numpy as np

logger = logging.getLogger("basketball-action")

FRAME_SIZE_FALLBACK = 112
NUM_FRAMES = 16
BOX_EXPAND = 1.2
MIN_WINDOW_FRAMES = 5
ZONE_GRID = 4  # 冷却键的空间网格（归一化 4×4 分区）：缓解跟踪 ID 碎片绕过冷却


class ActionRecognizer:
    """onnxruntime 动作分类器（16 帧 × 112 crop → 类别概率）。

    meta.json 与模型同目录约定同 text_clf_meta.json；会话与元数据懒加载，
    权重缺失时 is_available() 为 False，视频任务自动回退启发式事件。
    """

    def __init__(self, model_path: Path, meta_path: Path):
        self.model_path = Path(model_path)
        self.meta_path = Path(meta_path)
        self._session = None
        self._input_name = ""
        self.classes: list[str] = []
        self.zh_names: dict[str, str] = {}
        self.mean = np.array([0.43216, 0.394666, 0.37645], dtype=np.float32)
        self.std = np.array([0.22803, 0.22145, 0.216989], dtype=np.float32)
        self.background_class = "_none"

    def is_available(self) -> bool:
        if self._session is not None:
            return True
        if not (self.model_path.is_file() and self.meta_path.is_file()):
            return False
        try:
            import onnxruntime as ort

            self._session = ort.InferenceSession(
                str(self.model_path), providers=["CPUExecutionProvider"])
            self._input_name = self._session.get_inputs()[0].name
            meta = json.loads(self.meta_path.read_text(encoding="utf-8"))
            self.classes = list(meta["classes"])
            self.zh_names = dict(meta.get("zh_names", {}))
            self.background_class = meta.get("background_class", "_none")
            if "mean" in meta:
                self.mean = np.array(meta["mean"], dtype=np.float32)
            if "std" in meta:
                self.std = np.array(meta["std"], dtype=np.float32)
            return True
        except Exception:
            logger.exception("动作模型加载失败：%s", self.model_path)
            self._session = None
            return False

    def classify(self, frames: list[np.ndarray]) -> tuple[str, float]:
        """frames: BGR 帧列表（数量任意），内部拉伸/截断到 16 帧后推理。"""
        crops = [cv2.resize(f, (FRAME_SIZE_FALLBACK, FRAME_SIZE_FALLBACK)) for f in frames]
        clip = np.stack(crops).astype(np.float32) / 255.0          # (T,H,W,3)
        clip = clip.transpose(3, 0, 1, 2)                            # (3,T,H,W)
        clip = (clip - self.mean[:, None, None, None]) / self.std[:, None, None, None]
        pick = np.linspace(0, clip.shape[1] - 1, NUM_FRAMES).round().astype(int)
        clip = clip[:, pick]                                         # (3,16,H,W)
        logits = self._session.run(None, {self._input_name: clip[None]})[0][0]
        probs = np.exp(logits - logits.max())
        probs /= probs.sum()
        idx = int(probs.argmax())
        return self.classes[idx], float(probs[idx])


def _expand_square(cx: float, cy: float, w: float, h: float,
                   img_w: int, img_h: int) -> tuple[int, int, int, int] | None:
    # 与训练侧 build_clips._expand_square 同口径：先转像素再 max(w,h)*1.2。
    # 旧实现 max(w, h) * img_w 把归一化高按宽度放大（1280/720 ≈ 1.78×），crop 偏大。
    side = max(w * img_w, h * img_h) * BOX_EXPAND
    if side < 16:
        return None
    left = max(0.0, cx * img_w - side / 2)
    top = max(0.0, cy * img_h - side / 2)
    right = min(float(img_w), cx * img_w + side / 2)
    bottom = min(float(img_h), cy * img_h + side / 2)
    if right - left < 16 or bottom - top < 16:
        return None
    return int(left), int(top), int(right), int(bottom)


def iter_action_events(
    detections_path: Path,
    frame_loader: Callable[[list[int]], list[np.ndarray | None]],
    recognizer: ActionRecognizer,
    *,
    window_ms: int = 1000,
    stride_ms: int = 1000,
    conf_threshold: float = 0.6,
    cooldown_ms: int = 3000,
) -> Iterator[dict[str, Any]]:
    """按 track 滑窗识别动作并产出事件流。

    frame_loader(frame_idx 列表) 返回对应原始帧（BGR 或 None），
    生产实现走 cv2 seek，测试可注入桩。背景类不产出事件；
    同 (位置分区, 动作) 冷却 cooldown_ms——按 ZONE_GRID 网格而非 track_id，
    同一球员换新 track_id 后仍在原分区，不会绕过冷却。
    """
    tracks: dict[int, list[dict[str, Any]]] = {}
    image_size = (1280, 720)
    with detections_path.open("r", encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            frame = json.loads(line)
            image_size = (int(frame.get("image_w", 1280)), int(frame.get("image_h", 720)))
            for box in frame.get("boxes", []):
                tid = box.get("track_id")
                if tid is None:
                    continue
                tracks.setdefault(int(tid), []).append(
                    {"t_ms": int(frame.get("t_ms", 0)), "frame_idx": int(frame.get("frame_idx", 0)),
                     "cx": float(box["cx"]), "cy": float(box["cy"]),
                     "w": float(box["w"]), "h": float(box["h"])})
    if not tracks:
        return

    last_emitted: dict[tuple[int, int, str], int] = {}
    for tid in sorted(tracks):
        observations = sorted(tracks[tid], key=lambda o: o["t_ms"])
        start_ms = observations[0]["t_ms"]
        end_ms = observations[-1]["t_ms"]
        window_start = start_ms
        while window_start + window_ms <= end_ms + window_ms // 2:
            center_ms = window_start + window_ms // 2
            window = [o for o in observations
                      if window_start <= o["t_ms"] < window_start + window_ms]
            window_start += stride_ms
            if len(window) < MIN_WINDOW_FRAMES:
                continue
            frames = frame_loader([o["frame_idx"] for o in window])
            crops = []
            for obs, img in zip(window, frames):
                if img is None:
                    continue
                rect = _expand_square(obs["cx"], obs["cy"], obs["w"], obs["h"],
                                      img.shape[1], img.shape[0])
                if rect is None:
                    continue
                crops.append(img[rect[1]:rect[3], rect[0]:rect[2]])
            if len(crops) < MIN_WINDOW_FRAMES:
                continue
            label, prob = recognizer.classify(crops)
            if label == recognizer.background_class or prob < conf_threshold:
                continue
            zone = (int(window[-1]["cx"] * ZONE_GRID), int(window[-1]["cy"] * ZONE_GRID))
            if center_ms - last_emitted.get((*zone, label), -10**9) < cooldown_ms:
                continue
            last_emitted[(*zone, label)] = center_ms
            yield {
                "t_ms": center_ms,
                "type": "action",
                "source": "action_model",
                "action": label,
                "action_zh": recognizer.zh_names.get(label, label),
                "conf": round(prob, 3),
                "track_id": tid,
                "player_count": len(window),
            }


class VideoFrameLoader:
    """按需 seek 解码指定帧号（0 起）；带 32 帧小缓存——多 track 在相同时刻
    反复取同一批帧，命中率高（帧 ~2.7MB，缓存上限 ~90MB）。"""

    CACHE_LIMIT = 32

    def __init__(self, video_path: Path):
        self.cap = cv2.VideoCapture(str(video_path))
        self._pos = 0
        self._cache: dict[int, np.ndarray] = {}

    def __call__(self, frame_idxs: list[int]) -> list[np.ndarray | None]:
        out: list[np.ndarray | None] = []
        for idx in frame_idxs:
            if idx in self._cache:
                out.append(self._cache[idx])
                continue
            if not self.cap.isOpened() or idx < self._pos:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                ok, img = self.cap.read()
                self._pos = idx + 1 if ok else -1
            else:
                ok = False
                img = None
                while self._pos <= idx:
                    ok, img = self.cap.read()
                    self._pos += 1
                    if not ok:
                        break
            if ok and img is not None:
                if len(self._cache) >= self.CACHE_LIMIT:
                    self._cache.clear()
                self._cache[idx] = img
            out.append(img if ok else None)
        return out

    def close(self) -> None:
        self._cache.clear()
        self.cap.release()

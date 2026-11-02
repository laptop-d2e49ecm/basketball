from __future__ import annotations

import io
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image, ImageOps

from app.core.coords import normalize_xyxy
from app.core.errors import InputError, ModelError


def _nms(xyxy: np.ndarray, scores: np.ndarray, threshold: float) -> list[int]:
    order = scores.argsort()[::-1]
    keep: list[int] = []
    while order.size:
        index = int(order[0])
        keep.append(index)
        if order.size == 1:
            break
        rest = order[1:]
        x1 = np.maximum(xyxy[index, 0], xyxy[rest, 0])
        y1 = np.maximum(xyxy[index, 1], xyxy[rest, 1])
        x2 = np.minimum(xyxy[index, 2], xyxy[rest, 2])
        y2 = np.minimum(xyxy[index, 3], xyxy[rest, 3])
        intersection = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
        area_one = (xyxy[index, 2] - xyxy[index, 0]) * (xyxy[index, 3] - xyxy[index, 1])
        area_rest = (xyxy[rest, 2] - xyxy[rest, 0]) * (xyxy[rest, 3] - xyxy[rest, 1])
        iou = intersection / np.clip(area_one + area_rest - intersection, 1e-9, None)
        order = rest[iou <= threshold]
    return keep


class ImageDetector:
    """CPU ONNX INT8 detector for the standalone image detection API."""

    def __init__(self, model_path: Path, min_box_side_px: int = 8) -> None:
        options = ort.SessionOptions()
        options.intra_op_num_threads = 4
        options.inter_op_num_threads = 1
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(
            str(model_path), sess_options=options, providers=["CPUExecutionProvider"]
        )
        self.input_name = self.session.get_inputs()[0].name
        input_shape = self.session.get_inputs()[0].shape
        size = input_shape[-1]
        self.input_size = int(size) if isinstance(size, int) else 640
        self.min_box_side_px = min_box_side_px

    @staticmethod
    def _decode(data: bytes) -> np.ndarray:
        with Image.open(io.BytesIO(data)) as image:
            oriented = ImageOps.exif_transpose(image)
            return np.array(oriented.convert("RGB"))

    def _letterbox(self, image: np.ndarray) -> tuple[np.ndarray, tuple[float, int, int]]:
        height, width = image.shape[:2]
        scale = min(self.input_size / height, self.input_size / width)
        resized_width = round(width * scale)
        resized_height = round(height * scale)
        pad_x = (self.input_size - resized_width) / 2
        pad_y = (self.input_size - resized_height) / 2
        left, right = round(pad_x - 0.1), round(pad_x + 0.1)
        top, bottom = round(pad_y - 0.1), round(pad_y + 0.1)
        resized = np.asarray(
            Image.fromarray(image).resize((resized_width, resized_height), Image.Resampling.BILINEAR)
        )
        canvas = np.full((self.input_size, self.input_size, 3), 114, dtype=np.uint8)
        canvas[top : top + resized_height, left : left + resized_width] = resized
        tensor = canvas.astype(np.float32).transpose(2, 0, 1) / 255.0
        return np.ascontiguousarray(tensor[None]), (scale, left, top)

    def api_detect(self, data: bytes, conf: float = 0.25, iou: float = 0.55) -> dict:
        started = time.perf_counter()
        try:
            image = self._decode(data)
        except Exception as exc:
            raise InputError("图片无法解码，请检查文件是否损坏") from exc
        height, width = image.shape[:2]
        if min(height, width) < 32:
            raise InputError("图片尺寸过小，宽和高都必须至少为 32 像素")

        tensor, (scale, left, top) = self._letterbox(image)
        infer_started = time.perf_counter()
        try:
            output = self.session.run(None, {self.input_name: tensor})[0]
        except Exception as exc:
            raise ModelError("ONNX 图像检测推理失败") from exc
        infer_ms = (time.perf_counter() - infer_started) * 1000

        prediction = output[0].T if output.ndim == 3 else output
        boxes_center = prediction[:, :4].copy()
        scores = prediction[:, 4:].max(axis=1) if prediction.shape[1] > 5 else prediction[:, 4]
        selected = scores >= conf
        boxes_center, scores = boxes_center[selected], scores[selected]
        dropped = 0
        boxes_norm = np.zeros((0, 4), dtype=np.float32)
        kept_scores = np.zeros((0,), dtype=np.float32)

        if boxes_center.size:
            boxes_xyxy = np.stack(
                [
                    boxes_center[:, 0] - boxes_center[:, 2] / 2,
                    boxes_center[:, 1] - boxes_center[:, 3] / 2,
                    boxes_center[:, 0] + boxes_center[:, 2] / 2,
                    boxes_center[:, 1] + boxes_center[:, 3] / 2,
                ],
                axis=1,
            )
            keep = _nms(boxes_xyxy, scores, iou)
            boxes_xyxy, scores = boxes_xyxy[keep], scores[keep]
            boxes_xyxy[:, [0, 2]] = np.clip((boxes_xyxy[:, [0, 2]] - left) / scale, 0, width)
            boxes_xyxy[:, [1, 3]] = np.clip((boxes_xyxy[:, [1, 3]] - top) / scale, 0, height)
            side = np.minimum(boxes_xyxy[:, 2] - boxes_xyxy[:, 0], boxes_xyxy[:, 3] - boxes_xyxy[:, 1])
            valid = side >= self.min_box_side_px
            dropped = int((~valid).sum())
            boxes_xyxy, kept_scores = boxes_xyxy[valid], scores[valid]
            normalized = [normalize_xyxy(box, width, height) for box in boxes_xyxy]
            valid_normalized = [box for box in normalized if box is not None]
            if len(valid_normalized) != len(normalized):
                dropped += len(normalized) - len(valid_normalized)
                kept_scores = kept_scores[[box is not None for box in normalized]]
            boxes_norm = np.asarray(valid_normalized, dtype=np.float32).reshape(-1, 4)

        if boxes_norm.size and (
            (boxes_norm < 0).any()
            or (boxes_norm > 1).any()
            or (boxes_norm[:, 2:] <= 0).any()
        ):
            raise ModelError("检测模型返回了无效坐标")

        boxes = [
            {
                "cx": round(float(box[0]), 6),
                "cy": round(float(box[1]), 6),
                "w": round(float(box[2]), 6),
                "h": round(float(box[3]), 6),
                "conf": round(float(score), 4),
            }
            for box, score in zip(boxes_norm, kept_scores)
        ]
        return {
            "boxes": boxes,
            "player_count": len(boxes),
            "dropped_boxes": dropped,
            "image_w": width,
            "image_h": height,
            "conf_thr": conf,
            "iou_thr": iou,
            "infer_ms": round(infer_ms, 2),
            "total_ms": round((time.perf_counter() - started) * 1000, 2),
        }

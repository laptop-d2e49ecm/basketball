"""ONNX INT8 球员检测服务。

- letterbox/坐标还原口径与实验 3 `p2_delivery/scripts/infer.py` 完全一致（复制其
  letterbox_u8 的舍入规则），保证服务化前后精度口径不变；
- NMS 用 numpy 重写（nc=1 场景），使 API 进程摆脱 torch/ultralytics 依赖；
- 坐标输出遵守统一契约：归一化 cx,cy,w,h ∈[0,1]（见 core/coords.py）。
"""
from __future__ import annotations

import time

import numpy as np
import onnxruntime as ort
from PIL import Image

from ..core import coords as C
from ..core.config import DEFAULT_CONF, DEFAULT_IOU, MIN_BOX_SIDE_PX
from ..core.errors import ModelError


def nms_numpy(xyxy: np.ndarray, scores: np.ndarray, iou_thr: float) -> list[int]:
    """贪心 NMS（与 torchvision.ops.nms 在 nc=1 下等价），纯 numpy 实现。"""
    order = scores.argsort()[::-1]
    keep: list[int] = []
    while order.size > 0:
        i = int(order[0])
        keep.append(i)
        if order.size == 1:
            break
        rest = order[1:]
        xx1 = np.maximum(xyxy[i, 0], xyxy[rest, 0])
        yy1 = np.maximum(xyxy[i, 1], xyxy[rest, 1])
        xx2 = np.minimum(xyxy[i, 2], xyxy[rest, 2])
        yy2 = np.minimum(xyxy[i, 3], xyxy[rest, 3])
        inter = np.clip(xx2 - xx1, 0, None) * np.clip(yy2 - yy1, 0, None)
        a1 = (xyxy[i, 2] - xyxy[i, 0]) * (xyxy[i, 3] - xyxy[i, 1])
        a2 = (xyxy[rest, 2] - xyxy[rest, 0]) * (xyxy[rest, 3] - xyxy[rest, 1])
        ious = inter / np.clip(a1 + a2 - inter, 1e-9, None)
        order = rest[ious <= iou_thr]
    return keep


class Detector:
    """实验 3 INT8 模型的服务化封装（启动时加载一次）。"""

    def __init__(self, model_path, conf: float = DEFAULT_CONF, iou: float = DEFAULT_IOU,
                 threads: int = 4):
        opt = ort.SessionOptions()
        opt.intra_op_num_threads = threads
        opt.inter_op_num_threads = 1
        opt.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(str(model_path), sess_options=opt,
                                            providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name
        size = self.session.get_inputs()[0].shape[-1]
        self.input_size = int(size) if str(size).isdigit() else 640  # 动态轴回退导出尺寸 640
        self.conf, self.iou = conf, iou
        self.min_side_px = MIN_BOX_SIDE_PX

    # ---- 预处理（与实验 3 infer.py letterbox 同口径，PIL 解码免 cv2 依赖）----
    @staticmethod
    def decode_rgb(data: bytes) -> np.ndarray:
        img = Image.open(__import__("io").BytesIO(data)).convert("RGB")
        return np.asarray(img)

    def letterbox(self, im: np.ndarray):
        h, w = im.shape[:2]
        r = min(self.input_size / h, self.input_size / w)
        nw, nh = round(w * r), round(h * r)
        dw, dh = (self.input_size - nw) / 2, (self.input_size - nh) / 2
        left, right = round(dw - 0.1), round(dw + 0.1)
        top, bottom = round(dh - 0.1), round(dh + 0.1)
        resized = np.asarray(Image.fromarray(im).resize((nw, nh), Image.BILINEAR))
        out = np.full((self.input_size, self.input_size, 3), 114, dtype=np.uint8)
        out[top:top + nh, left:left + nw] = resized
        x = out.astype(np.float32).transpose(2, 0, 1) / 255.0   # HWC->CHW, RGB
        return np.ascontiguousarray(x[None]), (r, left, top, w, h)

    # ---- 推理与后处理 ----
    def infer_raw(self, img_rgb: np.ndarray) -> tuple[np.ndarray, tuple]:
        x, meta = self.letterbox(img_rgb)
        t0 = time.perf_counter()
        out = self.session.run(None, {self.input_name: x})[0]
        infer_ms = (time.perf_counter() - t0) * 1000
        return out, meta, infer_ms

    def predict(self, img_rgb: np.ndarray, conf: float | None = None,
                iou: float | None = None) -> dict:
        conf = self.conf if conf is None else float(np.clip(conf, 0.05, 0.9))
        iou = self.iou if iou is None else float(np.clip(iou, 0.3, 0.95))
        h0, w0 = img_rgb.shape[:2]
        out, (r, left, top, _, _), infer_ms = self.infer_raw(img_rgb)
        # YOLOv8 输出 [1, 4+nc, N] -> [N, 4+nc]，nc=1 时分数取第 5 行
        pred = out[0].T if out.ndim == 3 else out
        boxes_c = pred[:, :4].copy()                # 640 letterbox 空间 cxcywh
        scores = pred[:, 4:].max(axis=1) if pred.shape[1] > 5 else pred[:, 4]

        m = scores >= conf
        boxes_c, scores = boxes_c[m], scores[m]
        dropped = 0
        boxes_n = np.zeros((0, 4), dtype=np.float32)
        if boxes_c.size:
            xyxy = np.stack([boxes_c[:, 0] - boxes_c[:, 2] / 2,
                             boxes_c[:, 1] - boxes_c[:, 3] / 2,
                             boxes_c[:, 0] + boxes_c[:, 2] / 2,
                             boxes_c[:, 1] + boxes_c[:, 3] / 2], axis=1)
            keep = nms_numpy(xyxy, scores, iou)
            xyxy, scores = xyxy[keep], scores[keep]
            # letterbox 空间 -> 原图像素，越界裁剪（实验 1 出画框规则）
            xyxy[:, [0, 2]] = np.clip((xyxy[:, [0, 2]] - left) / r, 0, w0)
            xyxy[:, [1, 3]] = np.clip((xyxy[:, [1, 3]] - top) / r, 0, h0)
            # 过小框丢弃并计数（<MIN_BOX_SIDE_PX，沿用实验 1 阈值思想）
            side = np.minimum(xyxy[:, 2] - xyxy[:, 0], xyxy[:, 3] - xyxy[:, 1])
            good = side >= self.min_side_px
            dropped = int((~good).sum())
            boxes_n = C.xyxy_px_to_norm(xyxy[good], w0, h0)
        C.assert_valid_norm_boxes(boxes_n)          # 防线：越界/压扁即抛错
        return {
            "boxes": [
                {"cx": round(float(b[0]), 6), "cy": round(float(b[1]), 6),
                 "w": round(float(b[2]), 6), "h": round(float(b[3]), 6),
                 "conf": round(float(s), 4)}
                for b, s in zip(boxes_n, scores[good]) if boxes_n.size
            ],
            "player_count": int(len(boxes_n)),
            "dropped_boxes": dropped,
            "image_w": int(w0), "image_h": int(h0),
            "infer_ms": round(infer_ms, 2),
        }

    def api_detect(self, data: bytes, conf: float | None = None,
                   iou: float | None = None) -> dict:
        t0 = time.perf_counter()
        try:
            img = self.decode_rgb(data)
        except Exception as e:  # noqa: BLE001
            raise ModelError(f"图像解码失败: {e}") from e
        if min(img.shape[:2]) < 32:
            raise ModelError("图像尺寸过小（<32px），无法推理")
        result = self.predict(img, conf=conf, iou=iou)
        result["conf_thr"] = self.conf if conf is None else float(np.clip(conf, 0.05, 0.9))
        result["iou_thr"] = self.iou if iou is None else float(np.clip(iou, 0.3, 0.95))
        result["total_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        return result

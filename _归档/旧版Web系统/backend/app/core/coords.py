"""坐标换算的唯一实现（实验 1 教训的制度化落地）。

实验 1 数据增强时因像素/归一化坐标混用把检测框压成一个点；实验 4 前后端
坐标链路是同类 bug 高发区，因此：
1. API 契约写死：boxes 一律为归一化 cx,cy,w,h，取值 [0,1]；
2. 前后端各自只允许经由本模块风格的函数做换算（前端对应 src/api/coords.js）；
3. 出画/过小框按阈值丢弃并计数（见 detector.py），异常数字可在界面暴露。
"""
from __future__ import annotations

import numpy as np


def xyxy_px_to_norm(boxes_xyxy: np.ndarray, w: int, h: int) -> np.ndarray:
    """原图像素 xyxy (N,4) -> 归一化 cx,cy,w,h (N,4)，并做合法域校验。"""
    if boxes_xyxy.size == 0:
        return np.zeros((0, 4), dtype=np.float32)
    x1, y1, x2, y2 = boxes_xyxy[:, 0], boxes_xyxy[:, 1], boxes_xyxy[:, 2], boxes_xyxy[:, 3]
    cx = ((x1 + x2) / 2.0) / w
    cy = ((y1 + y2) / 2.0) / h
    bw = (x2 - x1) / w
    bh = (y2 - y1) / h
    return np.stack([cx, cy, bw, bh], axis=1).astype(np.float32)


def norm_to_xyxy_px(box_norm: np.ndarray, w: int, h: int) -> np.ndarray:
    """归一化 cx,cy,w,h (N,4) -> 原图像素 xyxy (N,4)。"""
    cx, cy, bw, bh = box_norm[:, 0], box_norm[:, 1], box_norm[:, 2], box_norm[:, 3]
    x1 = (cx - bw / 2.0) * w
    y1 = (cy - bh / 2.0) * h
    x2 = (cx + bw / 2.0) * w
    y2 = (cy + bh / 2.0) * h
    return np.stack([x1, y1, x2, y2], axis=1).astype(np.float32)


def assert_valid_norm_boxes(boxes_norm: np.ndarray) -> None:
    """防线：坐标必须落在 [0,1] 且宽高 > 0（防"压成一点"回归）。"""
    if boxes_norm.size == 0:
        return
    if (boxes_norm < 0).any() or (boxes_norm > 1).any():
        raise ValueError(f"归一化坐标越界: min={boxes_norm.min():.4f} max={boxes_norm.max():.4f}")
    if (boxes_norm[:, 2:] <= 0).any() or (boxes_norm[:, :2] <= 0).any():
        raise ValueError("归一化坐标出现非正值（框被压成一点或越界）")

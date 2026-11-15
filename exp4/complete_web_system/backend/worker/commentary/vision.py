# -*- coding: utf-8 -*-
"""视觉看帧：抓取事件时刻的关键帧，交视觉大模型客观描述画面（作为解说的第二事实源）。

设计要点：
1. 只在真正要生成解说的那条事件上抓帧（去重/上限护栏之后），小量随机访问开销可控；
2. 帧压缩到 768px 宽、JPEG 质量 70（约 60~100KB）再 base64，控制 token 与带宽；
3. 视觉调用失败/超时/未配置一律返回 None——解说自动降级为"结构化事实+风格参考"，不阻塞任务；
4. 模型客户端进程内复用；首次失败即熔断本进程（与 llm.py 的 _MODEL_FAILED 同策略）。
"""
from __future__ import annotations

import base64
import logging
import re
from typing import Any

import cv2

logger = logging.getLogger("basketball-worker.commentary.vision")

ANALYST_PROMPT = (
    "你是篮球比赛画面分析师，看一张比赛视频截图。"
    "用不超过 40 字客观描述：场上大致局面、球员正在做什么"
    "（如运球、护球、争抢、卡位、跑位、贴身防守；看不清动作就只描述站位，不硬猜）、"
    "球的大致位置。不许出现比分、球员姓名、球队名。直接输出描述，不要任何前后缀。"
)

_VISION = None
_VISION_FAILED = False


def _get_model() -> Any | None:
    """进程内复用的视觉模型客户端；初始化失败只记一次日志并熔断。"""
    global _VISION, _VISION_FAILED
    if _VISION is not None:
        return _VISION
    if _VISION_FAILED:
        return None
    try:
        from app.agent.providers import make_vision_model

        _VISION = make_vision_model()
        logger.info("vision 客户端已初始化（进程内复用）")
        return _VISION
    except Exception as exc:  # noqa: BLE001 - 配置缺失不影响主流程
        _VISION_FAILED = True
        logger.warning("vision 初始化失败，本任务不注入画面观察：%s", exc)
        return None


class FrameGrabber:
    """按时间点（毫秒）回读视频帧并编码为 base64 JPEG（仅解说阶段使用）。"""

    def __init__(self, video_path: str, width: int = 768) -> None:
        self._path = str(video_path)
        self._width = width
        self._cap: cv2.VideoCapture | None = None

    def _capture(self) -> cv2.VideoCapture | None:
        if self._cap is None:
            cap = cv2.VideoCapture(self._path)
            if not cap.isOpened():
                logger.warning("FrameGrabber 打不开视频：%s", self._path)
                return None
            self._cap = cap
        return self._cap

    def jpeg_b64(self, t_ms: float) -> str | None:
        cap = self._capture()
        if cap is None:
            return None
        cap.set(cv2.CAP_PROP_POS_MSEC, float(t_ms))
        ok, frame = cap.read()
        if not ok or frame is None:
            return None
        height, width = frame.shape[:2]
        if width > self._width:
            scale = self._width / float(width)
            frame = cv2.resize(
                frame,
                (self._width, max(1, int(round(height * scale)))),
                interpolation=cv2.INTER_AREA,
            )
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
        if not ok:
            return None
        return base64.b64encode(buf).decode("ascii")

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None


def describe_frame(jpeg_b64: str) -> str | None:
    """把一帧截图交给视觉大模型，返回不超过 60 字的画面描述；失败返回 None。"""
    global _VISION_FAILED
    model = _get_model()
    if model is None:
        return None
    try:
        content = [
            {"type": "text", "text": ANALYST_PROMPT},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{jpeg_b64}"}},
        ]
        msg = model.invoke([("user", content)])
        text = str(getattr(msg, "content", msg) or "").strip()
        text = re.sub(r"\s+", " ", text).strip()
        return text[:60] or None
    except Exception as exc:  # noqa: BLE001 - 任何失败都不阻塞解说
        _VISION_FAILED = True
        logger.warning("vision 调用失败，本进程熔断画面观察：%s", exc)
        return None

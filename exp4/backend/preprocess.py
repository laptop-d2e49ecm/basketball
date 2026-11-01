"""上传文件校验 —— 复用实验 1 清洗规则的服务化版本。

对应实验 1 `02_clean/clean_images.py` 的三步：扩展名白名单、损坏检测
（PIL verify）、EXIF 抹除（API 场景只解码不落盘，EXIF 天然不参与方向干扰）。
"""
from __future__ import annotations

import io

from PIL import Image

from app.core.config import ALLOWED_IMAGE_EXTS, ALLOWED_VIDEO_EXTS, MAX_UPLOAD_MB, MAX_VIDEO_MB
from app.core.errors import InputError


def check_image_bytes(filename: str, data: bytes) -> bytes:
    """图像白名单 + 大小限制 + 损坏检测；返回原始字节。"""
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_IMAGE_EXTS:
        raise InputError(f"图像格式错误，请上传 PNG/JPG（收到 {ext or '无扩展名'}）")
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise InputError(f"图像超过 {MAX_UPLOAD_MB}MB 限制")
    try:
        img = Image.open(io.BytesIO(data))
        img.verify()  # 损坏检测（实验 1 同款）
    except Exception as e:  # noqa: BLE001
        raise InputError("图像文件损坏或无法解码，请重新导出后上传") from e
    return data


def check_video_bytes(filename: str, data: bytes) -> bytes:
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_VIDEO_EXTS:
        raise InputError(f"视频格式错误，请上传 MP4/MOV/AVI（收到 {ext or '无扩展名'}）")
    if len(data) > MAX_VIDEO_MB * 1024 * 1024:
        raise InputError(f"视频超过 {MAX_VIDEO_MB}MB 限制")
    return data


def check_text(text: str | None) -> str:
    text = (text or "").strip()
    if not text:
        raise InputError("文本不能为空")
    if len(text) > 2000:
        raise InputError("文本超过 2000 字限制")
    return text

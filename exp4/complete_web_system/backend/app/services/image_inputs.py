from __future__ import annotations

import io
from pathlib import Path

from app.core.config import settings
from app.core.errors import InputError, ModelError

ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}


def check_image_bytes(filename: str, data: bytes) -> bytes:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_IMAGE_EXTENSIONS:
        raise InputError("图像格式错误，请上传 PNG 或 JPG 图片")
    if len(data) > settings.max_image_upload_bytes:
        limit_mb = settings.max_image_upload_bytes // (1024 * 1024)
        raise InputError(f"图片超过 {limit_mb} MB 限制")
    if not data:
        raise InputError("上传的图片为空")

    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as image:
            image.verify()
    except ImportError as exc:
        raise ModelError("缺少 Pillow 依赖，请按 requirements.txt 安装后重启服务") from exc
    except Exception as exc:
        raise InputError("图片文件损坏或无法解码，请重新导出后上传") from exc
    return data


def check_text(text: str | None) -> str:
    clean = (text or "").strip()
    if len(clean) > 2000:
        raise InputError("文本不能超过 2000 字")
    return clean

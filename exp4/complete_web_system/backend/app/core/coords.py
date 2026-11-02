from __future__ import annotations

import math
from collections.abc import Sequence


def normalize_xyxy(
    box: Sequence[float], image_width: int, image_height: int
) -> tuple[float, float, float, float] | None:
    """Convert pixel xyxy coordinates to normalized center xywh coordinates.

    Coordinates are clipped to the image bounds. Invalid image dimensions,
    non-finite coordinates, and boxes with no visible area are rejected.
    """
    if image_width <= 0 or image_height <= 0:
        raise ValueError("image dimensions must be positive")
    if len(box) != 4:
        raise ValueError("box must contain x1, y1, x2, y2")

    x1, y1, x2, y2 = (float(value) for value in box)
    if not all(math.isfinite(value) for value in (x1, y1, x2, y2)):
        raise ValueError("box coordinates must be finite")

    left = max(0.0, min(float(image_width), x1))
    top = max(0.0, min(float(image_height), y1))
    right = max(0.0, min(float(image_width), x2))
    bottom = max(0.0, min(float(image_height), y2))
    if right <= left or bottom <= top:
        return None

    return (
        ((left + right) / 2) / image_width,
        ((top + bottom) / 2) / image_height,
        (right - left) / image_width,
        (bottom - top) / image_height,
    )


def denormalize_cxcywh(
    box: Sequence[float], image_width: int, image_height: int
) -> tuple[float, float, float, float]:
    """Convert normalized center xywh coordinates to pixel xyxy coordinates."""
    if image_width <= 0 or image_height <= 0:
        raise ValueError("image dimensions must be positive")
    if len(box) != 4:
        raise ValueError("box must contain cx, cy, w, h")
    cx, cy, width, height = (float(value) for value in box)
    if not all(math.isfinite(value) for value in (cx, cy, width, height)):
        raise ValueError("box coordinates must be finite")
    return (
        (cx - width / 2) * image_width,
        (cy - height / 2) * image_height,
        (cx + width / 2) * image_width,
        (cy + height / 2) * image_height,
    )

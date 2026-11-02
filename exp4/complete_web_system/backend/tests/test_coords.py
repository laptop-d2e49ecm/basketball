from __future__ import annotations

import pytest

from app.core.coords import denormalize_cxcywh, normalize_xyxy


@pytest.mark.parametrize(
    ("xyxy", "width", "height"),
    [
        ((20, 10, 100, 70), 200, 100),
        ((0, 0, 200, 100), 200, 100),
        ((-10, 20, 60, 120), 200, 100),
        ((150, 30, 240, 90), 200, 100),
    ],
)
def test_pixel_normalized_round_trip(xyxy, width, height):
    normalized = normalize_xyxy(xyxy, width, height)
    assert normalized is not None
    restored = denormalize_cxcywh(normalized, width, height)
    clipped = (
        max(0, min(width, xyxy[0])),
        max(0, min(height, xyxy[1])),
        max(0, min(width, xyxy[2])),
        max(0, min(height, xyxy[3])),
    )
    assert restored == pytest.approx(clipped)
    assert all(0 <= value <= 1 for value in normalized)


@pytest.mark.parametrize("xyxy", [(10, 10, 10, 20), (10, 10, 20, 10), (-4, 1, -1, 5)])
def test_zero_visible_area_is_rejected(xyxy):
    assert normalize_xyxy(xyxy, 100, 80) is None


def test_invalid_dimensions_and_non_finite_coordinates_are_rejected():
    with pytest.raises(ValueError, match="dimensions"):
        normalize_xyxy((0, 0, 1, 1), 0, 80)
    with pytest.raises(ValueError, match="finite"):
        normalize_xyxy((0, 0, float("nan"), 1), 100, 80)

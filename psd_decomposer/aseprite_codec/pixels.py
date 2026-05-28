from __future__ import annotations

from .constants import COLOR_DEPTH_GRAYSCALE, COLOR_DEPTH_INDEXED, COLOR_DEPTH_RGBA
from .errors import AseUnsupportedFeatureError


def bytes_per_pixel(color_depth: int) -> int:
    """Aseprite color depth 값에 대응하는 픽셀당 바이트 수를 반환합니다."""

    if color_depth == COLOR_DEPTH_RGBA:
        return 4
    if color_depth == COLOR_DEPTH_GRAYSCALE:
        return 2
    if color_depth == COLOR_DEPTH_INDEXED:
        return 1
    raise AseUnsupportedFeatureError(f"지원하지 않는 color depth입니다: {color_depth}")

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PIL import Image

from .blend_modes import blend_mode_to_psd
from .document_backend import DocumentBackend, DocumentBackendError
from .models import LayerInfo


def write_layers_to_psd(
    document: DocumentBackend,
    layer_ids: tuple[str, ...],
    output_path: Path,
    *,
    preserve_canvas: bool,
    rescale: int = 100,
    layer_names: dict[str, str] | None = None,
) -> Path:
    """문서 백엔드가 렌더링한 1프레임 레이어 이미지를 새 PSD 파일로 저장합니다."""

    try:
        from psd_tools import PSDImage
    except ImportError as exc:
        raise DocumentBackendError("PSD 변환에는 psd-tools가 필요합니다.") from exc

    # 현재 Aseprite 백엔드는 frame_index=0만 렌더링하므로 멀티 프레임 입력도 첫 프레임만 PSD로 옮깁니다.
    scale = max(1, rescale) / 100
    canvas_size = _scaled_size(_psd_canvas_size(document, layer_ids, preserve_canvas), scale)
    psd = PSDImage.new("RGBA", canvas_size, (0, 0, 0, 0))

    # 문서 스택 순서를 보존하면서 선택된 레이어만 PSD 픽셀 레이어로 추가합니다.
    selected = set(layer_ids)
    for layer in document.layers:
        if layer.id not in selected:
            continue
        layer = _renamed_layer(layer, layer_names)
        image, left, top = _layer_image_and_offset(document, layer.id, preserve_canvas)
        image = _scaled_image(image, scale)
        left = round(left * scale)
        top = round(top * scale)

        # psd-tools 생성 API는 전달받은 이름을 구형 MacRoman 필드에 직접 넣으므로 먼저 안전한 이름으로 생성합니다.
        pixel_layer = psd.create_pixel_layer(image, name="Layer", top=top, left=left)
        # name setter를 거치면 MacRoman 대체값과 PSD Unicode 레이어명 태그(luni)가 함께 기록됩니다.
        pixel_layer.name = layer.name
        # 공통 모드가 PSD에 존재할 때 원본 레이어의 블렌드 모드를 새 픽셀 레이어에 보존합니다.
        psd_blend_mode = blend_mode_to_psd(layer.blend_mode)
        if psd_blend_mode is None:
            raise DocumentBackendError(f"PSD가 지원하지 않는 블렌드 모드입니다: {layer.blend_mode.value}")
        pixel_layer.blend_mode = psd_blend_mode

    output_path.parent.mkdir(parents=True, exist_ok=True)
    psd.save(output_path)
    return output_path


def _renamed_layer(layer: LayerInfo, layer_names: dict[str, str] | None) -> LayerInfo:
    """GUI에서 입력한 레이어명이 있으면 출력용 LayerInfo에 반영합니다."""

    if not layer_names:
        return layer
    name = layer_names.get(layer.id, "").strip()
    return replace(layer, name=name) if name else layer


def _psd_canvas_size(document: DocumentBackend, layer_ids: tuple[str, ...], preserve_canvas: bool) -> tuple[int, int]:
    """캔버스 보존 여부에 맞춰 새 PSD 문서의 크기를 계산합니다."""

    if preserve_canvas:
        return document.width, document.height

    # crop 출력에서는 선택 레이어 이미지의 실제 크기를 새 PSD 캔버스로 사용합니다.
    first_layer_id = layer_ids[0]
    image = document.render_layer(first_layer_id)
    return max(1, image.width), max(1, image.height)


def _layer_image_and_offset(document: DocumentBackend, layer_id: str, preserve_canvas: bool) -> tuple[Image.Image, int, int]:
    """PSD 픽셀 레이어에 넣을 이미지와 좌표를 준비합니다."""

    layer = document.get_layer_info(layer_id)
    image = document.render_layer(layer_id).convert("RGBA")
    if preserve_canvas:
        return image, layer.left, layer.top
    return image, 0, 0


def _scaled_size(size: tuple[int, int], scale: float) -> tuple[int, int]:
    """확대 비율을 적용한 PSD 캔버스 크기를 계산합니다."""

    width, height = size
    return max(1, round(width * scale)), max(1, round(height * scale))


def _scaled_image(image: Image.Image, scale: float) -> Image.Image:
    """확대 비율이 100%가 아닐 때 레이어 이미지를 리샘플링합니다."""

    if scale == 1:
        return image
    return image.resize(_scaled_size(image.size, scale), Image.Resampling.LANCZOS)

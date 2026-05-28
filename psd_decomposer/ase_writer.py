from __future__ import annotations

from pathlib import Path

from PIL import Image

from .aseprite_codec import encode_aseprite_file
from .aseprite_codec.constants import CEL_COMPRESSED_IMAGE, COLOR_DEPTH_RGBA
from .aseprite_codec.model import AseFrame, AseHeader, AsepriteFile, CelChunk, LayerChunk
from .document_backend import DocumentBackend


def write_layers_to_aseprite(
    document: DocumentBackend,
    layer_ids: tuple[str, ...],
    output_path: Path,
    *,
    preserve_canvas: bool,
    rescale: int = 100,
) -> Path:
    """문서 백엔드가 렌더링한 정적 레이어 이미지를 1프레임 Aseprite 파일로 저장합니다."""

    # PSD 원본은 프레임 개념이 없으므로 Aseprite 변환 결과도 첫 프레임 하나만 생성합니다.
    scale = max(1, rescale) / 100
    canvas_size = _scaled_size(_aseprite_canvas_size(document, layer_ids, preserve_canvas), scale)
    chunks: list[object] = []

    # 선택 레이어를 출력 파일의 연속 layer index로 다시 매핑합니다.
    selected = set(layer_ids)
    output_index = 0
    for layer in document.layers:
        if layer.id not in selected:
            continue
        chunks.append(
            LayerChunk(
                index=output_index,
                flags=1 if layer.visible else 0,
                visible=layer.visible,
                layer_type=0,
                child_level=0,
                blend_mode=0,
                opacity=255,
                name=layer.name,
                dirty=True,
            )
        )
        image, left, top = _layer_image_and_offset(document, layer.id, preserve_canvas)
        image = _scaled_image(image, scale)
        chunks.append(
            CelChunk(
                layer_index=output_index,
                x=round(left * scale),
                y=round(top * scale),
                opacity=255,
                cel_type=CEL_COMPRESSED_IMAGE,
                z_index=0,
                width=image.width,
                height=image.height,
                pixels=image.tobytes(),
                dirty=True,
            )
        )
        output_index += 1

    ase_file = AsepriteFile(
        header=_aseprite_header(canvas_size),
        frames=[AseFrame(index=0, size=0, duration_ms=100, chunks=chunks)],
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    encode_aseprite_file(ase_file, output_path)
    return output_path


def _aseprite_header(canvas_size: tuple[int, int]) -> AseHeader:
    """새 Aseprite 파일에 사용할 RGBA 헤더 기본값을 만듭니다."""

    width, height = canvas_size
    return AseHeader(
        file_size=0,
        frames=1,
        width=width,
        height=height,
        color_depth=COLOR_DEPTH_RGBA,
        flags=0,
        speed_deprecated=100,
        transparent_palette_index=0,
        color_count=0,
        pixel_width=1,
        pixel_height=1,
        grid_x=0,
        grid_y=0,
        grid_width=width,
        grid_height=height,
    )


def _aseprite_canvas_size(document: DocumentBackend, layer_ids: tuple[str, ...], preserve_canvas: bool) -> tuple[int, int]:
    """캔버스 보존 여부에 맞춰 새 Aseprite 문서의 크기를 계산합니다."""

    if preserve_canvas:
        return document.width, document.height

    # crop 출력에서는 선택 레이어 이미지의 실제 크기를 새 Aseprite 캔버스로 사용합니다.
    first_layer_id = layer_ids[0]
    image = document.render_layer(first_layer_id)
    return max(1, image.width), max(1, image.height)


def _layer_image_and_offset(document: DocumentBackend, layer_id: str, preserve_canvas: bool) -> tuple[Image.Image, int, int]:
    """Aseprite Cel에 넣을 이미지와 좌표를 준비합니다."""

    layer = document.get_layer_info(layer_id)
    image = document.render_layer(layer_id).convert("RGBA")
    if preserve_canvas:
        return image, layer.left, layer.top
    return image, 0, 0


def _scaled_size(size: tuple[int, int], scale: float) -> tuple[int, int]:
    """확대 비율을 적용한 Aseprite 캔버스 크기를 계산합니다."""

    width, height = size
    return max(1, round(width * scale)), max(1, round(height * scale))


def _scaled_image(image: Image.Image, scale: float) -> Image.Image:
    """확대 비율이 100%가 아닐 때 레이어 이미지를 리샘플링합니다."""

    if scale == 1:
        return image
    return image.resize(_scaled_size(image.size, scale), Image.Resampling.LANCZOS)

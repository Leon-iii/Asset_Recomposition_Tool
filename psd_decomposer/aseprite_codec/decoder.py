from __future__ import annotations

from pathlib import Path

from .binary import BinaryReader
from .chunks import parse_chunk, read_chunk_header
from .constants import CHUNK_LAYER, FILE_HEADER_SIZE, FILE_MAGIC, FRAME_HEADER_SIZE, FRAME_MAGIC, SUPPORTED_COLOR_DEPTHS
from .errors import AseFormatError, AseUnsupportedFeatureError
from .model import AseFrame, AseHeader, AsepriteFile, LayerChunk, PaletteChunk, TagsChunk, UnknownChunk


def decode_aseprite_file(path: Path) -> AsepriteFile:
    """파일 경로에서 Aseprite 바이너리를 읽어 중간 모델로 디코딩합니다."""

    return decode_aseprite_bytes(Path(path).read_bytes())


def decode_aseprite_bytes(data: bytes) -> AsepriteFile:
    """Aseprite 바이너리 bytes를 header, frame, raw chunk 모델로 디코딩합니다."""

    reader = BinaryReader(data)
    header = _read_header(reader)
    frames: list[AseFrame] = []
    unknown_chunks: list[UnknownChunk] = []
    layers = []
    tags = []
    palettes = []
    layer_index = 0

    for frame_index in range(header.frames):
        frame, layer_index = _read_frame(reader, frame_index, header=header, first_layer_index=layer_index)
        frames.append(frame)
        for chunk in frame.chunks:
            if isinstance(chunk, UnknownChunk):
                unknown_chunks.append(chunk)
            elif isinstance(chunk, LayerChunk):
                layers.append(chunk)
            elif isinstance(chunk, TagsChunk):
                tags.extend(chunk.tags)
            elif isinstance(chunk, PaletteChunk):
                palettes.append(chunk)

    if reader.tell() > header.file_size:
        raise AseFormatError("읽은 데이터가 header file size를 초과했습니다.")
    return AsepriteFile(
        header=header,
        frames=frames,
        layers=layers,
        tags=tags,
        palettes=palettes,
        unknown_chunks=unknown_chunks,
    )


def _read_header(reader: BinaryReader) -> AseHeader:
    start = reader.tell()
    file_size = reader.read_u32()
    magic = reader.read_u16()
    if magic != FILE_MAGIC:
        raise AseFormatError(f"Aseprite file magic이 아닙니다: 0x{magic:04X}")

    frames = reader.read_u16()
    width = reader.read_u16()
    height = reader.read_u16()
    color_depth = reader.read_u16()
    if color_depth not in SUPPORTED_COLOR_DEPTHS:
        raise AseUnsupportedFeatureError(f"지원하지 않는 color depth입니다: {color_depth}")

    flags = reader.read_u32()
    speed_deprecated = reader.read_u16()
    reader.read_u32()
    reader.read_u32()
    transparent_palette_index = reader.read_u8()
    reader.read_bytes(3)
    color_count = reader.read_u16()
    pixel_width = reader.read_u8()
    pixel_height = reader.read_u8()
    grid_x = reader.read_i16()
    grid_y = reader.read_i16()
    grid_width = reader.read_u16()
    grid_height = reader.read_u16()
    reader.read_bytes(84)

    if reader.tell() - start != FILE_HEADER_SIZE:
        raise AseFormatError("Aseprite file header는 128바이트여야 합니다.")

    return AseHeader(
        file_size=file_size,
        frames=frames,
        width=width,
        height=height,
        color_depth=color_depth,
        flags=flags,
        speed_deprecated=speed_deprecated,
        transparent_palette_index=transparent_palette_index,
        color_count=color_count,
        pixel_width=pixel_width,
        pixel_height=pixel_height,
        grid_x=grid_x,
        grid_y=grid_y,
        grid_width=grid_width,
        grid_height=grid_height,
    )


def _read_frame(reader: BinaryReader, frame_index: int, *, header: AseHeader, first_layer_index: int) -> tuple[AseFrame, int]:
    frame_start = reader.tell()
    frame_size = reader.read_u32()
    if frame_size < FRAME_HEADER_SIZE:
        raise AseFormatError(f"frame size는 {FRAME_HEADER_SIZE} 이상이어야 합니다: {frame_size}")
    frame_end = frame_start + frame_size
    if frame_end > reader.length:
        raise AseFormatError("frame size가 실제 파일 길이를 초과합니다.")

    magic = reader.read_u16()
    if magic != FRAME_MAGIC:
        raise AseFormatError(f"Aseprite frame magic이 아닙니다: 0x{magic:04X}")

    old_chunk_count = reader.read_u16()
    duration_ms = reader.read_u16()
    reader.read_bytes(2)
    new_chunk_count = reader.read_u32()
    chunk_count = _resolve_chunk_count(old_chunk_count, new_chunk_count)
    chunks: list[object] = []
    layer_index = first_layer_index

    for _ in range(chunk_count):
        chunk_header = read_chunk_header(reader)
        payload = reader.read_bytes(chunk_header.payload_size)
        chunk = parse_chunk(
            chunk_header,
            payload,
            file_flags=header.flags,
            color_depth=header.color_depth,
            layer_index=layer_index,
        )
        chunks.append(chunk)
        if chunk_header.chunk_type == CHUNK_LAYER:
            layer_index += 1

    if reader.tell() > frame_end:
        raise AseFormatError("frame chunk 데이터가 frame size를 초과했습니다.")
    reader.seek(frame_end)
    return AseFrame(index=frame_index, size=frame_size, duration_ms=duration_ms, chunks=chunks), layer_index


def _resolve_chunk_count(old_chunk_count: int, new_chunk_count: int) -> int:
    if old_chunk_count == 0xFFFF:
        return new_chunk_count
    if new_chunk_count != 0:
        return new_chunk_count
    return old_chunk_count

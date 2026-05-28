from __future__ import annotations

import zlib
from dataclasses import dataclass

from .binary import BinaryReader
from .constants import (
    CEL_COMPRESSED_IMAGE,
    CEL_COMPRESSED_TILEMAP,
    CEL_LINKED,
    CEL_RAW_IMAGE,
    CHUNK_CEL,
    CHUNK_HEADER_SIZE,
    CHUNK_LAYER,
    CHUNK_PALETTE,
    CHUNK_TAGS,
)
from .errors import AseFormatError
from .model import CelChunk, LayerChunk, PaletteChunk, PaletteEntry, Tag, TagsChunk, UnknownChunk
from .pixels import bytes_per_pixel


@dataclass(frozen=True)
class ChunkHeader:
    size: int
    chunk_type: int

    @property
    def payload_size(self) -> int:
        return self.size - CHUNK_HEADER_SIZE


def read_chunk_header(reader: BinaryReader) -> ChunkHeader:
    """Aseprite chunk header를 읽고 size 규칙을 검증합니다."""

    size = reader.read_u32()
    chunk_type = reader.read_u16()
    if size < CHUNK_HEADER_SIZE:
        raise AseFormatError(f"chunk size는 {CHUNK_HEADER_SIZE} 이상이어야 합니다: {size}")
    return ChunkHeader(size=size, chunk_type=chunk_type)


def read_unknown_chunk(reader: BinaryReader, header: ChunkHeader) -> UnknownChunk:
    """아직 지원하지 않는 chunk payload를 버리지 않고 보존합니다."""

    return UnknownChunk(size=header.size, chunk_type=header.chunk_type, payload=reader.read_bytes(header.payload_size))


def parse_chunk(
    header: ChunkHeader,
    payload: bytes,
    *,
    file_flags: int,
    color_depth: int,
    layer_index: int,
) -> object:
    """chunk type에 맞는 중간 모델로 payload를 파싱합니다."""

    if header.chunk_type == CHUNK_LAYER:
        return parse_layer_chunk(header, payload, file_flags=file_flags, layer_index=layer_index)
    if header.chunk_type == CHUNK_CEL:
        return parse_cel_chunk(header, payload, color_depth=color_depth)
    if header.chunk_type == CHUNK_TAGS:
        return parse_tags_chunk(header, payload)
    if header.chunk_type == CHUNK_PALETTE:
        return parse_palette_chunk(header, payload)
    return UnknownChunk(size=header.size, chunk_type=header.chunk_type, payload=payload)


def parse_layer_chunk(header: ChunkHeader, payload: bytes, *, file_flags: int, layer_index: int) -> LayerChunk:
    reader = BinaryReader(payload)
    flags = reader.read_u16()
    layer_type = reader.read_u16()
    child_level = reader.read_u16()
    reader.read_u16()
    reader.read_u16()
    blend_mode = reader.read_u16()
    opacity = reader.read_u8()
    reader.read_bytes(3)
    name = reader.read_string()
    tileset_index = reader.read_u32() if layer_type == 2 else None
    uuid = reader.read_bytes(16) if file_flags & 4 else None
    _ensure_payload_consumed(reader, payload)
    return LayerChunk(
        index=layer_index,
        flags=flags,
        visible=bool(flags & 1),
        layer_type=layer_type,
        child_level=child_level,
        blend_mode=blend_mode,
        opacity=opacity,
        name=name,
        tileset_index=tileset_index,
        uuid=uuid,
        raw_payload=payload,
        size=header.size,
    )


def parse_cel_chunk(header: ChunkHeader, payload: bytes, *, color_depth: int) -> CelChunk:
    reader = BinaryReader(payload)
    layer_index = reader.read_u16()
    x = reader.read_i16()
    y = reader.read_i16()
    opacity = reader.read_u8()
    cel_type = reader.read_u16()
    z_index = reader.read_i16()
    reader.read_bytes(5)

    width: int | None = None
    height: int | None = None
    pixels: bytes | None = None
    linked_frame: int | None = None
    compressed_payload: bytes | None = None

    if cel_type == CEL_RAW_IMAGE:
        width = reader.read_u16()
        height = reader.read_u16()
        pixels = reader.read_bytes(_expected_pixel_size(width, height, color_depth))
    elif cel_type == CEL_LINKED:
        linked_frame = reader.read_u16()
    elif cel_type == CEL_COMPRESSED_IMAGE:
        width = reader.read_u16()
        height = reader.read_u16()
        compressed_payload = reader.read_bytes(reader.length - reader.tell())
        try:
            pixels = zlib.decompress(compressed_payload)
        except zlib.error as exc:
            raise AseFormatError("압축 Cel payload를 zlib로 해제할 수 없습니다.") from exc
        expected_size = _expected_pixel_size(width, height, color_depth)
        if len(pixels) != expected_size:
            raise AseFormatError(f"압축 해제된 pixel 길이가 맞지 않습니다: {len(pixels)} != {expected_size}")
    elif cel_type == CEL_COMPRESSED_TILEMAP:
        raise AseFormatError("압축 tilemap Cel은 아직 지원하지 않습니다.")
    else:
        raise AseFormatError(f"알 수 없는 Cel type입니다: {cel_type}")

    _ensure_payload_consumed(reader, payload)
    return CelChunk(
        layer_index=layer_index,
        x=x,
        y=y,
        opacity=opacity,
        cel_type=cel_type,
        z_index=z_index,
        width=width,
        height=height,
        pixels=pixels,
        linked_frame=linked_frame,
        raw_payload=payload,
        compressed_payload=compressed_payload,
        size=header.size,
    )


def parse_tags_chunk(header: ChunkHeader, payload: bytes) -> TagsChunk:
    reader = BinaryReader(payload)
    tag_count = reader.read_u16()
    reader.read_bytes(8)
    tags: list[Tag] = []
    for _ in range(tag_count):
        from_frame = reader.read_u16()
        to_frame = reader.read_u16()
        loop_direction = reader.read_u8()
        repeat = reader.read_u16()
        reader.read_bytes(6)
        color_rgb = (reader.read_u8(), reader.read_u8(), reader.read_u8())
        reader.read_u8()
        name = reader.read_string()
        tags.append(
            Tag(
                from_frame=from_frame,
                to_frame=to_frame,
                loop_direction=loop_direction,
                repeat=repeat,
                name=name,
                color_rgb=color_rgb,
            )
        )
    _ensure_payload_consumed(reader, payload)
    return TagsChunk(tags=tags, raw_payload=payload, size=header.size)


def parse_palette_chunk(header: ChunkHeader, payload: bytes) -> PaletteChunk:
    reader = BinaryReader(payload)
    palette_size = reader.read_u32()
    first_index = reader.read_u32()
    last_index = reader.read_u32()
    reader.read_bytes(8)
    entries: list[PaletteEntry] = []
    for index in range(first_index, last_index + 1):
        flags = reader.read_u16()
        r = reader.read_u8()
        g = reader.read_u8()
        b = reader.read_u8()
        a = reader.read_u8()
        name = reader.read_string() if flags & 1 else None
        entries.append(PaletteEntry(index=index, r=r, g=g, b=b, a=a, name=name, flags=flags))
    _ensure_payload_consumed(reader, payload)
    return PaletteChunk(
        palette_size=palette_size,
        first_index=first_index,
        last_index=last_index,
        entries=entries,
        raw_payload=payload,
        size=header.size,
    )


def _expected_pixel_size(width: int, height: int, color_depth: int) -> int:
    if width <= 0 or height <= 0:
        raise AseFormatError(f"Cel width/height는 양수여야 합니다: {width}x{height}")
    return width * height * bytes_per_pixel(color_depth)


def _ensure_payload_consumed(reader: BinaryReader, payload: bytes) -> None:
    if reader.tell() != len(payload):
        raise AseFormatError("chunk payload를 정확히 끝까지 읽지 못했습니다.")

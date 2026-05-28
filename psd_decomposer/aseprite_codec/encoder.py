from __future__ import annotations

import zlib
from pathlib import Path

from .binary import BinaryWriter
from .constants import CEL_COMPRESSED_IMAGE, CEL_COMPRESSED_TILEMAP, CEL_LINKED, CEL_RAW_IMAGE, CHUNK_HEADER_SIZE, FILE_MAGIC, FRAME_MAGIC
from .errors import AseFormatError
from .model import AseFrame, AsepriteFile, CelChunk, LayerChunk, PaletteChunk, TagsChunk, UnknownChunk


def encode_aseprite_file(ase_file: AsepriteFile, path: Path) -> None:
    """Aseprite 중간 모델을 bytes로 인코딩해 파일에 저장합니다."""

    Path(path).write_bytes(encode_aseprite_bytes(ase_file))


def encode_aseprite_bytes(ase_file: AsepriteFile) -> bytes:
    """raw payload를 보존한 chunk들을 Aseprite 바이너리 bytes로 다시 조립합니다."""

    frame_payloads = [_encode_frame(frame) for frame in ase_file.frames]
    file_size = 128 + sum(len(frame_payload) for frame_payload in frame_payloads)

    writer = BinaryWriter()
    _write_header(writer, ase_file, file_size=file_size)
    for frame_payload in frame_payloads:
        writer.write_bytes(frame_payload)
    return writer.to_bytes()


def _write_header(writer: BinaryWriter, ase_file: AsepriteFile, *, file_size: int) -> None:
    header = ase_file.header
    writer.write_u32(file_size)
    writer.write_u16(FILE_MAGIC)
    writer.write_u16(len(ase_file.frames))
    writer.write_u16(header.width)
    writer.write_u16(header.height)
    writer.write_u16(header.color_depth)
    writer.write_u32(header.flags)
    writer.write_u16(header.speed_deprecated)
    writer.write_u32(0)
    writer.write_u32(0)
    writer.write_u8(header.transparent_palette_index)
    writer.write_bytes(b"\x00" * 3)
    writer.write_u16(header.color_count)
    writer.write_u8(header.pixel_width)
    writer.write_u8(header.pixel_height)
    writer.write_i16(header.grid_x)
    writer.write_i16(header.grid_y)
    writer.write_u16(header.grid_width)
    writer.write_u16(header.grid_height)
    writer.write_bytes(b"\x00" * 84)


def _encode_frame(frame: AseFrame) -> bytes:
    chunk_payloads = [_encode_chunk(chunk) for chunk in frame.chunks]
    frame_size = 16 + sum(len(chunk_payload) for chunk_payload in chunk_payloads)
    chunk_count = len(chunk_payloads)

    writer = BinaryWriter()
    writer.write_u32(frame_size)
    writer.write_u16(FRAME_MAGIC)
    if chunk_count <= 0xFFFF:
        writer.write_u16(chunk_count)
        new_chunk_count = 0
    else:
        writer.write_u16(0xFFFF)
        new_chunk_count = chunk_count
    writer.write_u16(frame.duration_ms)
    writer.write_bytes(b"\x00" * 2)
    writer.write_u32(new_chunk_count)
    for chunk_payload in chunk_payloads:
        writer.write_bytes(chunk_payload)
    return writer.to_bytes()


def _encode_chunk(chunk: object) -> bytes:
    chunk_type = _chunk_type(chunk)
    payload = _chunk_payload(chunk)
    writer = BinaryWriter()
    writer.write_u32(len(payload) + CHUNK_HEADER_SIZE)
    writer.write_u16(chunk_type)
    writer.write_bytes(payload)
    return writer.to_bytes()


def _chunk_type(chunk: object) -> int:
    chunk_type = getattr(chunk, "chunk_type", None)
    if isinstance(chunk_type, int):
        return chunk_type
    raise AseFormatError(f"인코딩할 수 없는 chunk 타입입니다: {type(chunk).__name__}")


def _chunk_payload(chunk: object) -> bytes:
    if isinstance(chunk, UnknownChunk):
        return chunk.payload
    if isinstance(chunk, LayerChunk):
        if chunk.dirty or chunk.raw_payload is None:
            return _encode_layer_payload(chunk)
        return chunk.raw_payload
    if isinstance(chunk, CelChunk):
        if chunk.dirty or chunk.raw_payload is None:
            return _encode_cel_payload(chunk)
        return chunk.raw_payload
    if isinstance(chunk, TagsChunk):
        if chunk.dirty or chunk.raw_payload is None:
            return _encode_tags_payload(chunk)
        return chunk.raw_payload
    if isinstance(chunk, PaletteChunk):
        if chunk.dirty or chunk.raw_payload is None:
            return _encode_palette_payload(chunk)
        return chunk.raw_payload
    raise AseFormatError(f"인코딩할 수 없는 chunk 타입입니다: {type(chunk).__name__}")


def _encode_layer_payload(chunk: LayerChunk) -> bytes:
    writer = BinaryWriter()
    writer.write_u16(chunk.flags)
    writer.write_u16(chunk.layer_type)
    writer.write_u16(chunk.child_level)
    writer.write_u16(0)
    writer.write_u16(0)
    writer.write_u16(chunk.blend_mode)
    writer.write_u8(chunk.opacity)
    writer.write_bytes(b"\x00" * 3)
    writer.write_string(chunk.name)
    if chunk.layer_type == 2:
        if chunk.tileset_index is None:
            raise AseFormatError("tilemap layer를 인코딩하려면 tileset_index가 필요합니다.")
        writer.write_u32(chunk.tileset_index)
    if chunk.uuid is not None:
        if len(chunk.uuid) != 16:
            raise AseFormatError("layer UUID는 16바이트여야 합니다.")
        writer.write_bytes(chunk.uuid)
    return writer.to_bytes()


def _encode_cel_payload(chunk: CelChunk) -> bytes:
    writer = BinaryWriter()
    writer.write_u16(chunk.layer_index)
    writer.write_i16(chunk.x)
    writer.write_i16(chunk.y)
    writer.write_u8(chunk.opacity)
    writer.write_u16(chunk.cel_type)
    writer.write_i16(chunk.z_index)
    writer.write_bytes(b"\x00" * 5)

    if chunk.cel_type == CEL_RAW_IMAGE:
        _write_cel_dimensions_and_pixels(writer, chunk, compressed=False)
    elif chunk.cel_type == CEL_LINKED:
        if chunk.linked_frame is None:
            raise AseFormatError("linked cel을 인코딩하려면 linked_frame이 필요합니다.")
        writer.write_u16(chunk.linked_frame)
    elif chunk.cel_type == CEL_COMPRESSED_IMAGE:
        _write_cel_dimensions_and_pixels(writer, chunk, compressed=True)
    elif chunk.cel_type == CEL_COMPRESSED_TILEMAP:
        raise AseFormatError("압축 tilemap Cel 인코딩은 아직 지원하지 않습니다.")
    else:
        raise AseFormatError(f"알 수 없는 Cel type입니다: {chunk.cel_type}")
    return writer.to_bytes()


def _write_cel_dimensions_and_pixels(writer: BinaryWriter, chunk: CelChunk, *, compressed: bool) -> None:
    if chunk.width is None or chunk.height is None or chunk.pixels is None:
        raise AseFormatError("이미지 Cel을 인코딩하려면 width, height, pixels가 필요합니다.")
    writer.write_u16(chunk.width)
    writer.write_u16(chunk.height)
    writer.write_bytes(zlib.compress(chunk.pixels) if compressed else chunk.pixels)


def _encode_tags_payload(chunk: TagsChunk) -> bytes:
    writer = BinaryWriter()
    writer.write_u16(len(chunk.tags))
    writer.write_bytes(b"\x00" * 8)
    for tag in chunk.tags:
        writer.write_u16(tag.from_frame)
        writer.write_u16(tag.to_frame)
        writer.write_u8(tag.loop_direction)
        writer.write_u16(tag.repeat)
        writer.write_bytes(b"\x00" * 6)
        color_rgb = tag.color_rgb or (0, 0, 0)
        if len(color_rgb) != 3:
            raise AseFormatError("tag color_rgb는 3개 값이어야 합니다.")
        for value in color_rgb:
            writer.write_u8(value)
        writer.write_u8(0)
        writer.write_string(tag.name)
    return writer.to_bytes()


def _encode_palette_payload(chunk: PaletteChunk) -> bytes:
    writer = BinaryWriter()
    writer.write_u32(chunk.palette_size)
    writer.write_u32(chunk.first_index)
    writer.write_u32(chunk.last_index)
    writer.write_bytes(b"\x00" * 8)
    for entry in chunk.entries:
        flags = entry.flags | (1 if entry.name is not None else 0)
        writer.write_u16(flags)
        writer.write_u8(entry.r)
        writer.write_u8(entry.g)
        writer.write_u8(entry.b)
        writer.write_u8(entry.a)
        if entry.name is not None:
            writer.write_string(entry.name)
    return writer.to_bytes()

from __future__ import annotations

import struct
import zlib

from psd_decomposer.aseprite_codec.constants import (
    CEL_COMPRESSED_IMAGE,
    CEL_LINKED,
    CEL_RAW_IMAGE,
    CHUNK_CEL,
    CHUNK_LAYER,
    CHUNK_PALETTE,
    CHUNK_TAGS,
    FILE_MAGIC,
    FRAME_MAGIC,
)


def pack_string(value: str) -> bytes:
    data = value.encode("utf-8")
    return struct.pack("<H", len(data)) + data


def make_header(
    *,
    file_size: int = 144,
    frames: int = 1,
    width: int = 16,
    height: int = 8,
    color_depth: int = 32,
) -> bytes:
    return b"".join(
        [
            struct.pack("<I", file_size),
            struct.pack("<H", FILE_MAGIC),
            struct.pack("<H", frames),
            struct.pack("<H", width),
            struct.pack("<H", height),
            struct.pack("<H", color_depth),
            struct.pack("<I", 0),
            struct.pack("<H", 100),
            struct.pack("<I", 0),
            struct.pack("<I", 0),
            struct.pack("<B", 0),
            b"\x00" * 3,
            struct.pack("<H", 0),
            struct.pack("<B", 1),
            struct.pack("<B", 1),
            struct.pack("<h", 0),
            struct.pack("<h", 0),
            struct.pack("<H", width),
            struct.pack("<H", height),
            b"\x00" * 84,
        ]
    )


def make_chunk(chunk_type: int, payload: bytes) -> bytes:
    return struct.pack("<IH", len(payload) + 6, chunk_type) + payload


def make_layer_payload(
    *,
    name: str,
    flags: int = 1,
    layer_type: int = 0,
    child_level: int = 0,
    blend_mode: int = 0,
    opacity: int = 255,
) -> bytes:
    return b"".join(
        [
            struct.pack("<H", flags),
            struct.pack("<H", layer_type),
            struct.pack("<H", child_level),
            struct.pack("<H", 0),
            struct.pack("<H", 0),
            struct.pack("<H", blend_mode),
            struct.pack("<B", opacity),
            b"\x00" * 3,
            pack_string(name),
        ]
    )


def make_layer_chunk(**kwargs) -> bytes:
    return make_chunk(CHUNK_LAYER, make_layer_payload(**kwargs))


def make_raw_cel_payload(
    *,
    layer_index: int,
    pixels: bytes,
    width: int = 1,
    height: int = 1,
    x: int = 0,
    y: int = 0,
    opacity: int = 255,
    z_index: int = 0,
) -> bytes:
    return _cel_common(layer_index, x, y, opacity, CEL_RAW_IMAGE, z_index) + struct.pack("<HH", width, height) + pixels


def make_compressed_cel_payload(
    *,
    layer_index: int,
    pixels: bytes,
    width: int = 1,
    height: int = 1,
    x: int = 0,
    y: int = 0,
    opacity: int = 255,
    z_index: int = 0,
) -> bytes:
    compressed = zlib.compress(pixels)
    return _cel_common(layer_index, x, y, opacity, CEL_COMPRESSED_IMAGE, z_index) + struct.pack("<HH", width, height) + compressed


def make_linked_cel_payload(*, layer_index: int, linked_frame: int, x: int = 0, y: int = 0, opacity: int = 255) -> bytes:
    return _cel_common(layer_index, x, y, opacity, CEL_LINKED, 0) + struct.pack("<H", linked_frame)


def make_cel_chunk(payload: bytes) -> bytes:
    return make_chunk(CHUNK_CEL, payload)


def make_tags_chunk(tags: list[dict]) -> bytes:
    payload = [struct.pack("<H", len(tags)), b"\x00" * 8]
    for tag in tags:
        payload.extend(
            [
                struct.pack("<H", tag["from_frame"]),
                struct.pack("<H", tag["to_frame"]),
                struct.pack("<B", tag.get("loop_direction", 0)),
                struct.pack("<H", tag.get("repeat", 0)),
                b"\x00" * 6,
                bytes(tag.get("color_rgb", (0, 0, 0))),
                b"\x00",
                pack_string(tag["name"]),
            ]
        )
    return make_chunk(CHUNK_TAGS, b"".join(payload))


def make_palette_chunk(entries: list[dict], *, palette_size: int | None = None, first_index: int = 0) -> bytes:
    palette_size = palette_size if palette_size is not None else len(entries)
    last_index = first_index + len(entries) - 1
    payload = [
        struct.pack("<I", palette_size),
        struct.pack("<I", first_index),
        struct.pack("<I", last_index),
        b"\x00" * 8,
    ]
    for entry in entries:
        name = entry.get("name")
        flags = 1 if name else 0
        payload.extend(
            [
                struct.pack("<H", flags),
                struct.pack("<B", entry["r"]),
                struct.pack("<B", entry["g"]),
                struct.pack("<B", entry["b"]),
                struct.pack("<B", entry["a"]),
            ]
        )
        if name:
            payload.append(pack_string(name))
    return make_chunk(CHUNK_PALETTE, b"".join(payload))


def _cel_common(layer_index: int, x: int, y: int, opacity: int, cel_type: int, z_index: int) -> bytes:
    return b"".join(
        [
            struct.pack("<H", layer_index),
            struct.pack("<h", x),
            struct.pack("<h", y),
            struct.pack("<B", opacity),
            struct.pack("<H", cel_type),
            struct.pack("<h", z_index),
            b"\x00" * 5,
        ]
    )


def make_frame(*, chunks: list[bytes] | None = None, duration_ms: int = 90, old_count: int | None = None) -> bytes:
    chunks = chunks or []
    frame_size = 16 + sum(len(chunk) for chunk in chunks)
    old_chunk_count = len(chunks) if old_count is None else old_count
    return b"".join(
        [
            struct.pack("<I", frame_size),
            struct.pack("<H", FRAME_MAGIC),
            struct.pack("<H", old_chunk_count),
            struct.pack("<H", duration_ms),
            b"\x00" * 2,
            struct.pack("<I", 0),
            *chunks,
        ]
    )


def make_aseprite_bytes(*, header: bytes | None = None, frames: list[bytes] | None = None) -> bytes:
    frames = frames if frames is not None else [make_frame()]
    frame_count = len(frames)
    body = b"".join(frames)
    if header is None:
        header = make_header(file_size=128 + len(body), frames=frame_count)
    return header + body

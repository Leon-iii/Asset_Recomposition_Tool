from __future__ import annotations

from dataclasses import dataclass, field

from .constants import CHUNK_CEL, CHUNK_LAYER, CHUNK_PALETTE, CHUNK_TAGS


@dataclass(frozen=True)
class AseHeader:
    file_size: int
    frames: int
    width: int
    height: int
    color_depth: int
    flags: int
    speed_deprecated: int
    transparent_palette_index: int
    color_count: int
    pixel_width: int
    pixel_height: int
    grid_x: int
    grid_y: int
    grid_width: int
    grid_height: int


@dataclass(frozen=True)
class UnknownChunk:
    size: int
    chunk_type: int
    payload: bytes


@dataclass(frozen=True)
class AseFrame:
    index: int
    size: int
    duration_ms: int
    chunks: list[object] = field(default_factory=list)

    @property
    def cels(self) -> list[CelChunk]:
        """frame 안에 들어 있는 Cel chunk 목록을 반환합니다."""

        return [chunk for chunk in self.chunks if isinstance(chunk, CelChunk)]

    @property
    def chunk_types(self) -> list[int]:
        """frame 안에 들어 있는 chunk type 목록을 순서대로 반환합니다."""

        return [chunk.chunk_type for chunk in self.chunks]


@dataclass(frozen=True)
class LayerChunk:
    index: int
    flags: int
    visible: bool
    layer_type: int
    child_level: int
    blend_mode: int
    opacity: int
    name: str
    tileset_index: int | None = None
    uuid: bytes | None = None
    raw_payload: bytes | None = None
    dirty: bool = False
    size: int = 0

    @property
    def chunk_type(self) -> int:
        return CHUNK_LAYER


@dataclass(frozen=True)
class CelChunk:
    layer_index: int
    x: int
    y: int
    opacity: int
    cel_type: int
    z_index: int
    width: int | None = None
    height: int | None = None
    pixels: bytes | None = None
    linked_frame: int | None = None
    raw_payload: bytes | None = None
    compressed_payload: bytes | None = None
    dirty: bool = False
    size: int = 0

    @property
    def chunk_type(self) -> int:
        return CHUNK_CEL


@dataclass(frozen=True)
class Tag:
    from_frame: int
    to_frame: int
    loop_direction: int
    repeat: int
    name: str
    color_rgb: tuple[int, int, int] | None = None


@dataclass(frozen=True)
class TagsChunk:
    tags: list[Tag]
    raw_payload: bytes | None = None
    dirty: bool = False
    size: int = 0

    @property
    def chunk_type(self) -> int:
        return CHUNK_TAGS


@dataclass(frozen=True)
class PaletteEntry:
    index: int
    r: int
    g: int
    b: int
    a: int
    name: str | None = None
    flags: int = 0


@dataclass(frozen=True)
class PaletteChunk:
    palette_size: int
    first_index: int
    last_index: int
    entries: list[PaletteEntry]
    raw_payload: bytes | None = None
    dirty: bool = False
    size: int = 0

    @property
    def chunk_type(self) -> int:
        return CHUNK_PALETTE


@dataclass(frozen=True)
class AsepriteFile:
    header: AseHeader
    frames: list[AseFrame]
    layers: list[LayerChunk] = field(default_factory=list)
    tags: list[Tag] = field(default_factory=list)
    palettes: list[PaletteChunk] = field(default_factory=list)
    unknown_chunks: list[UnknownChunk] = field(default_factory=list)

    @property
    def chunk_types_by_frame(self) -> list[list[int]]:
        """파일 전체의 frame별 chunk type 목록을 반환합니다."""

        return [frame.chunk_types for frame in self.frames]

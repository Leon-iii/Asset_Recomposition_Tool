from __future__ import annotations

import struct
from io import BytesIO

from .errors import AseFormatError


class BinaryReader:
    """Aseprite의 little-endian 기본 타입을 안전하게 읽는 reader입니다."""

    def __init__(self, data: bytes) -> None:
        self.length = len(data)
        self._stream = BytesIO(data)

    def tell(self) -> int:
        return self._stream.tell()

    def seek(self, offset: int) -> None:
        self._stream.seek(offset)

    def read_bytes(self, size: int) -> bytes:
        if size < 0:
            raise AseFormatError(f"음수 크기는 읽을 수 없습니다: {size}")
        data = self._stream.read(size)
        if len(data) != size:
            raise AseFormatError(f"예상한 {size}바이트를 읽지 못했습니다.")
        return data

    def read_u8(self) -> int:
        return self._unpack("<B", 1)

    def read_u16(self) -> int:
        return self._unpack("<H", 2)

    def read_i16(self) -> int:
        return self._unpack("<h", 2)

    def read_u32(self) -> int:
        return self._unpack("<I", 4)

    def read_i32(self) -> int:
        return self._unpack("<i", 4)

    def read_u64(self) -> int:
        return self._unpack("<Q", 8)

    def read_i64(self) -> int:
        return self._unpack("<q", 8)

    def read_string(self) -> str:
        length = self.read_u16()
        return self.read_bytes(length).decode("utf-8")

    def _unpack(self, fmt: str, size: int) -> int:
        try:
            return struct.unpack(fmt, self.read_bytes(size))[0]
        except struct.error as exc:
            raise AseFormatError(str(exc)) from exc


class BinaryWriter:
    """Aseprite의 little-endian 기본 타입을 bytes로 누적하는 writer입니다."""

    def __init__(self) -> None:
        self._stream = BytesIO()

    def tell(self) -> int:
        return self._stream.tell()

    def to_bytes(self) -> bytes:
        return self._stream.getvalue()

    def write_bytes(self, data: bytes) -> None:
        self._stream.write(data)

    def write_u8(self, value: int) -> None:
        self._pack("<B", value)

    def write_u16(self, value: int) -> None:
        self._pack("<H", value)

    def write_i16(self, value: int) -> None:
        self._pack("<h", value)

    def write_u32(self, value: int) -> None:
        self._pack("<I", value)

    def write_i32(self, value: int) -> None:
        self._pack("<i", value)

    def write_u64(self, value: int) -> None:
        self._pack("<Q", value)

    def write_i64(self, value: int) -> None:
        self._pack("<q", value)

    def write_string(self, value: str) -> None:
        data = value.encode("utf-8")
        self.write_u16(len(data))
        self.write_bytes(data)

    def _pack(self, fmt: str, value: int) -> None:
        try:
            self.write_bytes(struct.pack(fmt, value))
        except struct.error as exc:
            raise AseFormatError(str(exc)) from exc

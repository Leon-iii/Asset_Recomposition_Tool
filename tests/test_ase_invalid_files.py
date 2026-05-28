from __future__ import annotations

import struct
import unittest

from psd_decomposer.aseprite_codec import decode_aseprite_bytes
from psd_decomposer.aseprite_codec.errors import AseFormatError

from .ase_fixtures import make_aseprite_bytes, make_chunk, make_frame, make_header


class AseInvalidFileTests(unittest.TestCase):
    def test_wrong_frame_magic_number_raises_format_error(self) -> None:
        frame = bytearray(make_frame())
        frame[4:6] = b"\x00\x00"

        with self.assertRaises(AseFormatError):
            decode_aseprite_bytes(make_aseprite_bytes(frames=[bytes(frame)]))

    def test_truncated_frame_header_raises_format_error(self) -> None:
        data = make_header(file_size=132, frames=1) + struct.pack("<I", 16)

        with self.assertRaises(AseFormatError):
            decode_aseprite_bytes(data)

    def test_truncated_chunk_payload_raises_format_error(self) -> None:
        chunk = make_chunk(0x1111, b"abcd")[:-1]
        data = make_aseprite_bytes(frames=[make_frame(chunks=[chunk])])

        with self.assertRaises(AseFormatError):
            decode_aseprite_bytes(data)

    def test_frame_size_smaller_than_header_raises_format_error(self) -> None:
        frame = struct.pack("<I", 15) + b"\x00" * 11
        data = make_header(file_size=128 + len(frame), frames=1) + frame

        with self.assertRaises(AseFormatError):
            decode_aseprite_bytes(data)

    def test_frame_size_larger_than_available_data_raises_format_error(self) -> None:
        frame = bytearray(make_frame())
        frame[0:4] = struct.pack("<I", len(frame) + 1)
        data = make_header(file_size=128 + len(frame), frames=1) + bytes(frame)

        with self.assertRaises(AseFormatError):
            decode_aseprite_bytes(data)


if __name__ == "__main__":
    unittest.main()

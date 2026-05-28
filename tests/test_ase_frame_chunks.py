from __future__ import annotations

import struct
import unittest

from psd_decomposer.aseprite_codec import decode_aseprite_bytes
from psd_decomposer.aseprite_codec.chunks import read_chunk_header
from psd_decomposer.aseprite_codec.binary import BinaryReader
from psd_decomposer.aseprite_codec.errors import AseFormatError

from .ase_fixtures import make_aseprite_bytes, make_chunk, make_frame, make_header


class AseFrameChunkDecoderTests(unittest.TestCase):
    def test_chunk_size_includes_size_and_type_fields(self) -> None:
        reader = BinaryReader(make_chunk(0x1234, b"abc"))

        header = read_chunk_header(reader)

        self.assertEqual(header.size, 9)
        self.assertEqual(header.payload_size, 3)
        self.assertEqual(header.chunk_type, 0x1234)

    def test_unknown_chunks_are_preserved_not_dropped(self) -> None:
        chunk = make_chunk(0x7777, b"payload")
        data = make_aseprite_bytes(frames=[make_frame(chunks=[chunk])])

        ase_file = decode_aseprite_bytes(data)

        self.assertEqual(len(ase_file.frames[0].chunks), 1)
        self.assertEqual(ase_file.frames[0].chunks[0].chunk_type, 0x7777)
        self.assertEqual(ase_file.frames[0].chunks[0].payload, b"payload")
        self.assertEqual(ase_file.unknown_chunks[0].payload, b"payload")

    def test_frame_duration_and_index_are_decoded(self) -> None:
        data = make_aseprite_bytes(frames=[make_frame(duration_ms=123)])

        ase_file = decode_aseprite_bytes(data)

        self.assertEqual(ase_file.frames[0].index, 0)
        self.assertEqual(ase_file.frames[0].duration_ms, 123)

    def test_new_chunk_count_is_used_when_old_chunk_count_is_ffff(self) -> None:
        chunk = make_chunk(0x9999, b"x")
        frame_size = 16 + len(chunk)
        frame = b"".join(
            [
                struct.pack("<I", frame_size),
                struct.pack("<H", 0xF1FA),
                struct.pack("<H", 0xFFFF),
                struct.pack("<H", 60),
                b"\x00" * 2,
                struct.pack("<I", 1),
                chunk,
            ]
        )
        data = make_header(file_size=128 + len(frame), frames=1) + frame

        ase_file = decode_aseprite_bytes(data)

        self.assertEqual(len(ase_file.frames[0].chunks), 1)

    def test_chunk_size_smaller_than_header_raises_format_error(self) -> None:
        bad_chunk = struct.pack("<IH", 5, 0x1111)
        data = make_aseprite_bytes(frames=[make_frame(chunks=[bad_chunk])])

        with self.assertRaises(AseFormatError):
            decode_aseprite_bytes(data)


if __name__ == "__main__":
    unittest.main()

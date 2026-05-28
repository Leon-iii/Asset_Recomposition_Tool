from __future__ import annotations

import struct
import unittest

from psd_decomposer.aseprite_codec.binary import BinaryReader
from psd_decomposer.aseprite_codec.errors import AseFormatError

from .ase_fixtures import pack_string


class AseBinaryReaderTests(unittest.TestCase):
    def test_little_endian_integer_readers_use_aseprite_byte_order(self) -> None:
        data = b"".join(
            [
                struct.pack("<B", 0xFE),
                struct.pack("<H", 0x1234),
                struct.pack("<h", -2),
                struct.pack("<I", 0x12345678),
                struct.pack("<i", -3),
            ]
        )
        reader = BinaryReader(data)

        self.assertEqual(reader.read_u8(), 0xFE)
        self.assertEqual(reader.read_u16(), 0x1234)
        self.assertEqual(reader.read_i16(), -2)
        self.assertEqual(reader.read_u32(), 0x12345678)
        self.assertEqual(reader.read_i32(), -3)

    def test_string_is_word_length_prefixed_utf8_not_null_terminated(self) -> None:
        reader = BinaryReader(pack_string("레이어"))

        self.assertEqual(reader.read_string(), "레이어")

    def test_truncated_input_raises_format_error_instead_of_generic_crash(self) -> None:
        reader = BinaryReader(b"\x01")

        with self.assertRaises(AseFormatError):
            reader.read_u16()

    def test_read_bytes_rejects_negative_size(self) -> None:
        reader = BinaryReader(b"")

        with self.assertRaises(AseFormatError):
            reader.read_bytes(-1)


if __name__ == "__main__":
    unittest.main()

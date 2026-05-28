from __future__ import annotations

import unittest

from psd_decomposer.aseprite_codec import decode_aseprite_bytes
from psd_decomposer.aseprite_codec.errors import AseFormatError, AseUnsupportedFeatureError

from .ase_fixtures import make_aseprite_bytes, make_header


class AseHeaderDecoderTests(unittest.TestCase):
    def test_header_fields_are_decoded_from_128_byte_file_header(self) -> None:
        data = make_aseprite_bytes(header=make_header(width=32, height=24, color_depth=32))

        ase_file = decode_aseprite_bytes(data)

        self.assertEqual(ase_file.header.width, 32)
        self.assertEqual(ase_file.header.height, 24)
        self.assertEqual(ase_file.header.color_depth, 32)
        self.assertEqual(ase_file.header.frames, 1)
        self.assertEqual(len(ase_file.frames), 1)

    def test_empty_file_raises_format_error(self) -> None:
        with self.assertRaises(AseFormatError):
            decode_aseprite_bytes(b"")

    def test_truncated_file_header_raises_format_error(self) -> None:
        with self.assertRaises(AseFormatError):
            decode_aseprite_bytes(make_header()[:20])

    def test_wrong_file_magic_number_raises_format_error(self) -> None:
        header = bytearray(make_header())
        header[4:6] = b"\x00\x00"

        with self.assertRaises(AseFormatError):
            decode_aseprite_bytes(make_aseprite_bytes(header=bytes(header)))

    def test_unsupported_color_depth_raises_unsupported_feature_error(self) -> None:
        with self.assertRaises(AseUnsupportedFeatureError):
            decode_aseprite_bytes(make_aseprite_bytes(header=make_header(color_depth=24)))


if __name__ == "__main__":
    unittest.main()

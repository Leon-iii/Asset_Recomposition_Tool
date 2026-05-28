from __future__ import annotations

import struct
import unittest

from psd_decomposer.aseprite_codec import decode_aseprite_bytes
from psd_decomposer.aseprite_codec.constants import CEL_COMPRESSED_IMAGE, CEL_LINKED, CEL_RAW_IMAGE
from psd_decomposer.aseprite_codec.errors import AseFormatError

from .ase_fixtures import (
    make_aseprite_bytes,
    make_cel_chunk,
    make_compressed_cel_payload,
    make_frame,
    make_header,
    make_layer_chunk,
    make_linked_cel_payload,
    make_raw_cel_payload,
)


class AseCelChunkTests(unittest.TestCase):
    def test_raw_cel_uses_exact_pixel_count_from_color_depth(self) -> None:
        pixels = bytes([255, 0, 0, 255, 0, 255, 0, 255])
        data = make_aseprite_bytes(
            frames=[
                make_frame(
                    chunks=[
                        make_layer_chunk(name="Layer"),
                        make_cel_chunk(make_raw_cel_payload(layer_index=0, pixels=pixels, width=2, height=1, x=3, y=-2)),
                    ]
                )
            ]
        )

        cel = decode_aseprite_bytes(data).frames[0].cels[0]

        self.assertEqual(cel.layer_index, 0)
        self.assertEqual(cel.cel_type, CEL_RAW_IMAGE)
        self.assertEqual((cel.x, cel.y), (3, -2))
        self.assertEqual((cel.width, cel.height), (2, 1))
        self.assertEqual(cel.pixels, pixels)

    def test_compressed_cel_uses_zlib_and_exact_pixel_count(self) -> None:
        pixels = bytes([1, 2, 3, 4])
        data = make_aseprite_bytes(
            frames=[
                make_frame(
                    chunks=[
                        make_layer_chunk(name="Layer"),
                        make_cel_chunk(make_compressed_cel_payload(layer_index=0, pixels=pixels)),
                    ]
                )
            ]
        )

        cel = decode_aseprite_bytes(data).frames[0].cels[0]

        self.assertEqual(cel.cel_type, CEL_COMPRESSED_IMAGE)
        self.assertEqual(cel.pixels, pixels)
        self.assertIsNotNone(cel.compressed_payload)

    def test_linked_cel_references_a_frame_without_pixel_payload(self) -> None:
        data = make_aseprite_bytes(
            frames=[
                make_frame(chunks=[make_layer_chunk(name="Layer")]),
                make_frame(chunks=[make_cel_chunk(make_linked_cel_payload(layer_index=0, linked_frame=0))]),
            ]
        )

        cel = decode_aseprite_bytes(data).frames[1].cels[0]

        self.assertEqual(cel.cel_type, CEL_LINKED)
        self.assertEqual(cel.linked_frame, 0)
        self.assertIsNone(cel.pixels)

    def test_invalid_zlib_compressed_cel_payload_raises_format_error(self) -> None:
        payload = (
            struct.pack("<HhhB", 0, 0, 0, 255)
            + struct.pack("<Hh", CEL_COMPRESSED_IMAGE, 0)
            + b"\x00" * 5
            + struct.pack("<HH", 1, 1)
            + b"not-zlib"
        )
        data = make_aseprite_bytes(frames=[make_frame(chunks=[make_layer_chunk(name="Layer"), make_cel_chunk(payload)])])

        with self.assertRaises(AseFormatError):
            decode_aseprite_bytes(data)

    def test_decompressed_pixel_data_length_mismatch_raises_format_error(self) -> None:
        pixels = bytes([1, 2, 3, 4])
        data = make_aseprite_bytes(
            header=make_header(width=1, height=1, color_depth=32),
            frames=[
                make_frame(
                    chunks=[
                        make_layer_chunk(name="Layer"),
                        make_cel_chunk(make_compressed_cel_payload(layer_index=0, pixels=pixels, width=2, height=1)),
                    ]
                )
            ],
        )

        with self.assertRaises(AseFormatError):
            decode_aseprite_bytes(data)


if __name__ == "__main__":
    unittest.main()

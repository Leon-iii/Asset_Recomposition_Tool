from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path

from psd_decomposer.aseprite_codec import decode_aseprite_bytes, decode_aseprite_file, encode_aseprite_bytes
from psd_decomposer.aseprite_codec.constants import CEL_COMPRESSED_IMAGE
from psd_decomposer.aseprite_codec.binary import BinaryWriter
from psd_decomposer.aseprite_codec.errors import AseFormatError
from psd_decomposer.aseprite_codec.model import CelChunk, PaletteEntry, Tag

from .ase_fixtures import make_aseprite_bytes, make_cel_chunk, make_compressed_cel_payload, make_frame, make_layer_chunk


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "aseprite"


class AseBinaryWriterTests(unittest.TestCase):
    def test_little_endian_writers_match_aseprite_byte_order(self) -> None:
        writer = BinaryWriter()

        writer.write_u8(0x12)
        writer.write_u16(0x3456)
        writer.write_i16(-2)
        writer.write_u32(0x789ABCDE)
        writer.write_string("Layer")

        self.assertEqual(
            writer.to_bytes(),
            b"\x12\x56\x34\xfe\xff\xde\xbc\x9a\x78\x05\x00Layer",
        )

    def test_integer_overflow_raises_format_error(self) -> None:
        writer = BinaryWriter()

        with self.assertRaises(AseFormatError):
            writer.write_u8(256)


class AseEncoderTests(unittest.TestCase):
    def test_unknown_chunk_fixture_round_trips_to_identical_bytes(self) -> None:
        data = (FIXTURE_DIR / "header_frame_unknown_chunks.aseprite").read_bytes()
        ase_file = decode_aseprite_bytes(data)

        encoded = encode_aseprite_bytes(ase_file)

        self.assertEqual(encoded, data)

    def test_known_chunk_fixture_round_trips_to_equivalent_model(self) -> None:
        ase_file = decode_aseprite_file(FIXTURE_DIR / "layer_tag_palette_cel.aseprite")

        encoded = encode_aseprite_bytes(ase_file)
        decoded = decode_aseprite_bytes(encoded)

        self.assertEqual(decoded.header.file_size, len(encoded))
        self.assertEqual(decoded.header.frames, len(ase_file.frames))
        self.assertEqual(decoded.header.width, ase_file.header.width)
        self.assertEqual(decoded.header.height, ase_file.header.height)
        self.assertEqual(decoded.chunk_types_by_frame, ase_file.chunk_types_by_frame)
        self.assertEqual([layer.name for layer in decoded.layers], [layer.name for layer in ase_file.layers])
        self.assertEqual([(tag.name, tag.from_frame, tag.to_frame) for tag in decoded.tags], [("Idle", 0, 0)])
        self.assertEqual(decoded.frames[0].cels[0].pixels, ase_file.frames[0].cels[0].pixels)

    def test_frame_size_and_file_size_are_recalculated_from_current_frames(self) -> None:
        ase_file = decode_aseprite_file(FIXTURE_DIR / "layer_tag_palette_cel.aseprite")
        shortened_file = replace(ase_file, frames=ase_file.frames[:1], layers=ase_file.layers[:1])

        encoded = encode_aseprite_bytes(shortened_file)
        decoded = decode_aseprite_bytes(encoded)

        self.assertEqual(decoded.header.file_size, len(encoded))
        self.assertEqual(decoded.header.frames, 1)
        self.assertEqual(decoded.frames[0].size, len(encoded) - 128)

    def test_dirty_layer_chunk_is_serialized_from_fields(self) -> None:
        ase_file = decode_aseprite_file(FIXTURE_DIR / "layer_tag_palette_cel.aseprite")
        dirty_layer = replace(ase_file.frames[0].chunks[0], name="Renamed", raw_payload=None, dirty=True)
        dirty_frame = replace(ase_file.frames[0], chunks=[dirty_layer, *ase_file.frames[0].chunks[1:]])
        dirty_file = replace(ase_file, frames=[dirty_frame])

        decoded = decode_aseprite_bytes(encode_aseprite_bytes(dirty_file))

        self.assertEqual(decoded.layers[0].name, "Renamed")

    def test_dirty_raw_cel_chunk_is_serialized_from_fields(self) -> None:
        ase_file = decode_aseprite_file(FIXTURE_DIR / "layer_tag_palette_cel.aseprite")
        dirty_cel = replace(ase_file.frames[0].chunks[1], x=0, y=0, pixels=b"\x00\xff\x00\xff", raw_payload=None, dirty=True)
        dirty_frame = replace(ase_file.frames[0], chunks=[ase_file.frames[0].chunks[0], dirty_cel, *ase_file.frames[0].chunks[2:]])
        dirty_file = replace(ase_file, frames=[dirty_frame])

        decoded = decode_aseprite_bytes(encode_aseprite_bytes(dirty_file))

        self.assertEqual((decoded.frames[0].cels[0].x, decoded.frames[0].cels[0].y), (0, 0))
        self.assertEqual(decoded.frames[0].cels[0].pixels, b"\x00\xff\x00\xff")

    def test_dirty_compressed_cel_chunk_is_serialized_from_fields(self) -> None:
        data = make_aseprite_bytes(
            frames=[
                make_frame(
                    chunks=[
                        make_layer_chunk(name="Compressed"),
                        make_cel_chunk(
                            make_compressed_cel_payload(
                                layer_index=0,
                                pixels=b"\xff\x00\x00\xff",
                                width=1,
                                height=1,
                            )
                        ),
                    ]
                )
            ]
        )
        ase_file = decode_aseprite_bytes(data)
        dirty_cel = replace(ase_file.frames[0].cels[0], pixels=b"\x00\x00\xff\xff", raw_payload=None, dirty=True)
        dirty_frame = replace(ase_file.frames[0], chunks=[ase_file.frames[0].chunks[0], dirty_cel])
        dirty_file = replace(ase_file, frames=[dirty_frame])

        decoded = decode_aseprite_bytes(encode_aseprite_bytes(dirty_file))

        self.assertEqual(decoded.frames[0].cels[0].cel_type, CEL_COMPRESSED_IMAGE)
        self.assertEqual(decoded.frames[0].cels[0].pixels, b"\x00\x00\xff\xff")
        self.assertIsNotNone(decoded.frames[0].cels[0].compressed_payload)

    def test_dirty_tags_chunk_is_serialized_from_fields(self) -> None:
        ase_file = decode_aseprite_file(FIXTURE_DIR / "layer_tag_palette_cel.aseprite")
        dirty_tags = replace(
            ase_file.frames[0].chunks[2],
            tags=[Tag(from_frame=0, to_frame=0, loop_direction=1, repeat=2, name="Loop", color_rgb=(1, 2, 3))],
            raw_payload=None,
            dirty=True,
        )
        dirty_frame = replace(ase_file.frames[0], chunks=[*ase_file.frames[0].chunks[:2], dirty_tags, ase_file.frames[0].chunks[3]])
        dirty_file = replace(ase_file, frames=[dirty_frame])

        decoded = decode_aseprite_bytes(encode_aseprite_bytes(dirty_file))

        self.assertEqual(decoded.tags[0].name, "Loop")
        self.assertEqual(decoded.tags[0].loop_direction, 1)
        self.assertEqual(decoded.tags[0].repeat, 2)
        self.assertEqual(decoded.tags[0].color_rgb, (1, 2, 3))

    def test_dirty_palette_chunk_is_serialized_from_fields(self) -> None:
        ase_file = decode_aseprite_file(FIXTURE_DIR / "layer_tag_palette_cel.aseprite")
        dirty_palette = replace(
            ase_file.frames[0].chunks[3],
            entries=[PaletteEntry(index=0, r=0, g=0, b=255, a=255, name="blue")],
            raw_payload=None,
            dirty=True,
        )
        dirty_frame = replace(ase_file.frames[0], chunks=[*ase_file.frames[0].chunks[:3], dirty_palette])
        dirty_file = replace(ase_file, frames=[dirty_frame])

        decoded = decode_aseprite_bytes(encode_aseprite_bytes(dirty_file))

        self.assertEqual(decoded.palettes[0].entries[0].r, 0)
        self.assertEqual(decoded.palettes[0].entries[0].b, 255)
        self.assertEqual(decoded.palettes[0].entries[0].name, "blue")

    def test_dirty_linked_cel_requires_linked_frame(self) -> None:
        cel = CelChunk(layer_index=0, x=0, y=0, opacity=255, cel_type=1, z_index=0, dirty=True)
        ase_file = decode_aseprite_file(FIXTURE_DIR / "layer_tag_palette_cel.aseprite")
        dirty_frame = replace(ase_file.frames[0], chunks=[ase_file.frames[0].chunks[0], cel])
        dirty_file = replace(ase_file, frames=[dirty_frame])

        with self.assertRaises(AseFormatError):
            encode_aseprite_bytes(dirty_file)


if __name__ == "__main__":
    unittest.main()

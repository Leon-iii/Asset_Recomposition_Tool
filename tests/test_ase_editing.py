from __future__ import annotations

import unittest
from pathlib import Path

from psd_decomposer.aseprite_codec import (
    AseEditError,
    decode_aseprite_bytes,
    decode_aseprite_file,
    encode_aseprite_bytes,
    rename_layer,
    rename_layer_by_name,
    set_layer_visibility,
    set_layer_visibility_by_name,
)
from psd_decomposer.aseprite_codec.model import LayerChunk

from .ase_fixtures import make_aseprite_bytes, make_frame, make_layer_chunk


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "aseprite"


class AseEditingTests(unittest.TestCase):
    def test_rename_layer_updates_layer_views_and_encoded_output(self) -> None:
        ase_file = decode_aseprite_file(FIXTURE_DIR / "layer_tag_palette_cel.aseprite")

        edited = rename_layer(ase_file, 0, "Hero")
        decoded = decode_aseprite_bytes(encode_aseprite_bytes(edited))

        self.assertEqual(ase_file.layers[0].name, "Sprite")
        self.assertEqual(edited.layers[0].name, "Hero")
        self.assertTrue(edited.layers[0].dirty)
        self.assertEqual(_frame_layers(edited)[0].name, "Hero")
        self.assertEqual(decoded.layers[0].name, "Hero")

    def test_rename_layer_by_unique_name_uses_matching_layer(self) -> None:
        ase_file = decode_aseprite_file(FIXTURE_DIR / "layer_tag_palette_cel.aseprite")

        edited = rename_layer_by_name(ase_file, "Sprite", "Hero")

        self.assertEqual(edited.layers[0].name, "Hero")

    def test_set_layer_visibility_updates_flag_and_encoded_output(self) -> None:
        ase_file = decode_aseprite_file(FIXTURE_DIR / "layer_tag_palette_cel.aseprite")

        hidden = set_layer_visibility(ase_file, 0, False)
        decoded_hidden = decode_aseprite_bytes(encode_aseprite_bytes(hidden))
        shown = set_layer_visibility(hidden, 0, True)
        decoded_shown = decode_aseprite_bytes(encode_aseprite_bytes(shown))

        self.assertTrue(ase_file.layers[0].visible)
        self.assertFalse(hidden.layers[0].visible)
        self.assertEqual(hidden.layers[0].flags & 1, 0)
        self.assertFalse(decoded_hidden.layers[0].visible)
        self.assertTrue(shown.layers[0].visible)
        self.assertEqual(shown.layers[0].flags & 1, 1)
        self.assertTrue(decoded_shown.layers[0].visible)

    def test_set_layer_visibility_by_unique_name_uses_matching_layer(self) -> None:
        ase_file = decode_aseprite_file(FIXTURE_DIR / "layer_tag_palette_cel.aseprite")

        edited = set_layer_visibility_by_name(ase_file, "Sprite", False)

        self.assertFalse(edited.layers[0].visible)

    def test_missing_layer_index_raises_edit_error(self) -> None:
        ase_file = decode_aseprite_file(FIXTURE_DIR / "layer_tag_palette_cel.aseprite")

        with self.assertRaises(AseEditError):
            rename_layer(ase_file, 99, "Missing")

    def test_duplicate_layer_name_raises_edit_error(self) -> None:
        data = make_aseprite_bytes(
            frames=[
                make_frame(
                    chunks=[
                        make_layer_chunk(name="Duplicate"),
                        make_layer_chunk(name="Duplicate"),
                    ]
                )
            ]
        )
        ase_file = decode_aseprite_bytes(data)

        with self.assertRaises(AseEditError):
            rename_layer_by_name(ase_file, "Duplicate", "Renamed")

    def test_empty_layer_name_raises_edit_error(self) -> None:
        ase_file = decode_aseprite_file(FIXTURE_DIR / "layer_tag_palette_cel.aseprite")

        with self.assertRaises(AseEditError):
            rename_layer(ase_file, 0, "")


def _frame_layers(ase_file):
    return [chunk for frame in ase_file.frames for chunk in frame.chunks if isinstance(chunk, LayerChunk)]


if __name__ == "__main__":
    unittest.main()

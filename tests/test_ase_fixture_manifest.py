from __future__ import annotations

import json
import unittest
from pathlib import Path

from psd_decomposer.aseprite_codec import decode_aseprite_file
from psd_decomposer.aseprite_codec.constants import SUPPORTED_COLOR_DEPTHS


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "aseprite"


class AseFixtureManifestTests(unittest.TestCase):
    def test_header_frame_and_chunk_type_list_match_fixture_manifest(self) -> None:
        manifest_path = FIXTURE_DIR / "header_frame_unknown_chunks.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        ase_file = decode_aseprite_file(FIXTURE_DIR / manifest["file"])

        self.assertEqual(ase_file.header.width, manifest["canvas"]["width"])
        self.assertEqual(ase_file.header.height, manifest["canvas"]["height"])
        self.assertEqual(ase_file.header.color_depth, manifest["color_depth"])
        self.assertEqual(ase_file.header.frames, manifest["frame_count"])
        self.assertEqual(len(ase_file.frames), manifest["frame_count"])
        self.assertEqual([frame.duration_ms for frame in ase_file.frames], manifest["frame_durations"])
        self.assertEqual(ase_file.chunk_types_by_frame, manifest["chunk_types_by_frame"])

    def test_valid_fixture_invariants_hold_for_unknown_chunk_phase(self) -> None:
        manifest_path = FIXTURE_DIR / "header_frame_unknown_chunks.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        ase_file = decode_aseprite_file(FIXTURE_DIR / manifest["file"])

        self.assertEqual(ase_file.header.frames, len(ase_file.frames))
        self.assertIn(ase_file.header.color_depth, SUPPORTED_COLOR_DEPTHS)
        self.assertEqual(len(ase_file.unknown_chunks), len(manifest["unknown_chunks"]))
        for expected, chunk in zip(manifest["unknown_chunks"], ase_file.unknown_chunks, strict=True):
            self.assertEqual(chunk.chunk_type, expected["chunk_type"])
            self.assertEqual(chunk.payload.hex(), expected["payload_hex"])
            self.assertEqual(chunk.size, len(chunk.payload) + 6)

    def test_layer_tag_palette_and_cel_fixture_matches_manifest(self) -> None:
        manifest_path = FIXTURE_DIR / "layer_tag_palette_cel.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        ase_file = decode_aseprite_file(FIXTURE_DIR / manifest["file"])

        self.assertEqual(ase_file.header.width, manifest["canvas"]["width"])
        self.assertEqual(ase_file.header.height, manifest["canvas"]["height"])
        self.assertEqual(ase_file.chunk_types_by_frame, manifest["chunk_types_by_frame"])

        self.assertEqual(len(ase_file.layers), len(manifest["layers"]))
        for actual, expected in zip(ase_file.layers, manifest["layers"], strict=True):
            self.assertEqual(actual.index, expected["index"])
            self.assertEqual(actual.name, expected["name"])
            self.assertEqual(actual.visible, expected["visible"])
            self.assertEqual(actual.layer_type, expected["layer_type"])
            self.assertEqual(actual.child_level, expected["child_level"])
            self.assertEqual(actual.opacity, expected["opacity"])

        cels = [cel for frame in ase_file.frames for cel in frame.cels]
        self.assertEqual(len(cels), len(manifest["cels"]))
        for actual, expected in zip(cels, manifest["cels"], strict=True):
            self.assertEqual(actual.layer_index, expected["layer_index"])
            self.assertEqual((actual.x, actual.y), (expected["x"], expected["y"]))
            self.assertEqual((actual.width, actual.height), (expected["width"], expected["height"]))
            self.assertEqual(actual.cel_type, expected["cel_type"])
            self.assertEqual(actual.opacity, expected["opacity"])
            self.assertEqual(actual.pixels.hex(), expected["pixels_hex"])

        self.assertEqual([tag.name for tag in ase_file.tags], [tag["name"] for tag in manifest["tags"]])
        self.assertEqual(len(ase_file.palettes), len(manifest["palettes"]))
        palette = ase_file.palettes[0]
        expected_palette = manifest["palettes"][0]
        self.assertEqual(palette.palette_size, expected_palette["palette_size"])
        self.assertEqual((palette.first_index, palette.last_index), (expected_palette["first_index"], expected_palette["last_index"]))
        self.assertEqual(palette.entries[0].name, expected_palette["entries"][0]["name"])


if __name__ == "__main__":
    unittest.main()

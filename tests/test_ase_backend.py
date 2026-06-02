from __future__ import annotations

import unittest
from pathlib import Path
from uuid import uuid4

from psd_decomposer.ase_backend import AsepriteDocument
from psd_decomposer.aseprite_codec import decode_aseprite_file
from psd_decomposer.document_backend import DocumentBackendError, DocumentFormat, load_document

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "aseprite"
WORKSPACE_DIR = Path(__file__).resolve().parents[1]


class AsepriteDocumentTests(unittest.TestCase):
    def test_load_document_returns_aseprite_document_for_aseprite_file(self) -> None:
        document = load_document(FIXTURE_DIR / "layer_tag_palette_cel.aseprite")

        self.assertIsInstance(document, AsepriteDocument)
        self.assertEqual(document.format, DocumentFormat.ASEPRITE)

    def test_collect_layers_maps_frame_zero_cel_bounds_to_layer_info(self) -> None:
        document = AsepriteDocument(FIXTURE_DIR / "layer_tag_palette_cel.aseprite")

        self.assertEqual(len(document.layers), 1)
        layer = document.layers[0]
        self.assertEqual(layer.id, "0")
        self.assertEqual(layer.name, "Sprite")
        self.assertTrue(layer.visible)
        self.assertEqual((layer.left, layer.top), (1, 2))
        self.assertEqual((layer.width, layer.height), (1, 1))

    def test_frame_count_uses_decoded_frame_list_length(self) -> None:
        document = AsepriteDocument(FIXTURE_DIR / "header_frame_unknown_chunks.aseprite")

        self.assertEqual(document.frame_count, 2)

    def test_render_layer_returns_cel_sized_rgba_image(self) -> None:
        document = AsepriteDocument(FIXTURE_DIR / "layer_tag_palette_cel.aseprite")

        image = document.render_layer("0")

        self.assertEqual(image.size, (1, 1))
        self.assertEqual(image.getpixel((0, 0)), (255, 0, 0, 255))

    def test_render_preview_composites_visible_frame_zero_cels_on_canvas(self) -> None:
        document = AsepriteDocument(FIXTURE_DIR / "layer_tag_palette_cel.aseprite")

        image = document.render_preview()

        self.assertEqual(image.size, (4, 4))
        self.assertEqual(image.getpixel((1, 2)), (255, 0, 0, 255))
        self.assertEqual(image.getpixel((0, 0)), (0, 0, 0, 0))

    def test_render_preview_thumbnail_composites_scaled_frame_zero_cels(self) -> None:
        document = AsepriteDocument(FIXTURE_DIR / "layer_tag_palette_cel.aseprite")

        image = document.render_preview_thumbnail((2, 2))

        self.assertEqual(image.size, (2, 2))
        self.assertEqual(image.getpixel((0, 1)), (255, 0, 0, 255))
        self.assertEqual(image.getpixel((0, 0)), (0, 0, 0, 0))

    def test_render_preview_thumbnail_does_not_upscale_small_canvas(self) -> None:
        document = AsepriteDocument(FIXTURE_DIR / "layer_tag_palette_cel.aseprite")

        image = document.render_preview_thumbnail((8, 8))

        self.assertEqual(image.size, (4, 4))

    def test_render_layer_thumbnail_keeps_image_within_requested_size(self) -> None:
        document = AsepriteDocument(FIXTURE_DIR / "layer_tag_palette_cel.aseprite")

        image = document.render_layer_thumbnail("0", max_size=(8, 8))

        self.assertLessEqual(image.width, 8)
        self.assertLessEqual(image.height, 8)

    def test_child_level_builds_layer_info_group_path(self) -> None:
        document = AsepriteDocument(FIXTURE_DIR / "group_child.aseprite")

        self.assertEqual(document.layers[0].path, ())
        self.assertEqual(document.layers[1].path, ("Group",))

    def test_non_rgba_rendering_raises_document_backend_error(self) -> None:
        document = AsepriteDocument(FIXTURE_DIR / "indexed_render_unsupported.aseprite")

        with self.assertRaises(DocumentBackendError):
            document.render_layer("0")

    def test_rename_layer_and_save_as_persists_encoded_output(self) -> None:
        output_path = WORKSPACE_DIR / f"test-renamed-{uuid4().hex}.aseprite"
        try:
            document = AsepriteDocument(FIXTURE_DIR / "layer_tag_palette_cel.aseprite")
            layer = document.rename_layer("0", "Hero")
            saved_path = document.save_as(output_path)
            decoded = decode_aseprite_file(output_path)
        finally:
            output_path.unlink(missing_ok=True)

        self.assertEqual(layer.name, "Hero")
        self.assertEqual(saved_path, output_path)
        self.assertEqual(document.path, output_path)
        self.assertEqual(decoded.layers[0].name, "Hero")

    def test_set_layer_visibility_and_save_persists_encoded_output(self) -> None:
        output_path = WORKSPACE_DIR / f"test-hidden-{uuid4().hex}.aseprite"
        try:
            document = AsepriteDocument(FIXTURE_DIR / "layer_tag_palette_cel.aseprite")
            document.save_as(output_path)
            layer = document.set_layer_visibility("0", False)
            document.save()
            decoded = decode_aseprite_file(output_path)
        finally:
            output_path.unlink(missing_ok=True)

        self.assertFalse(layer.visible)
        self.assertFalse(decoded.layers[0].visible)

    def test_save_rejects_non_aseprite_output_extension(self) -> None:
        document = AsepriteDocument(FIXTURE_DIR / "layer_tag_palette_cel.aseprite")
        output_path = WORKSPACE_DIR / f"test-invalid-{uuid4().hex}.png"

        with self.assertRaises(DocumentBackendError):
            document.save_as(output_path)

    def test_editing_unknown_layer_id_raises_document_backend_error(self) -> None:
        document = AsepriteDocument(FIXTURE_DIR / "layer_tag_palette_cel.aseprite")

        with self.assertRaises(DocumentBackendError):
            document.rename_layer("missing", "Hero")


if __name__ == "__main__":
    unittest.main()

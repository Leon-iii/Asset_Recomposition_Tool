from __future__ import annotations

import unittest
from unittest.mock import Mock

from PIL import Image

from psd_decomposer.psd_backend import PsdDocument


class PsdBackendTests(unittest.TestCase):
    def test_render_preview_composites_on_transparent_canvas_without_embedded_preview(self) -> None:
        document = PsdDocument.__new__(PsdDocument)
        preview = Image.new("RGB", (2, 2), (255, 0, 0))
        document._psd = Mock()
        document._psd.composite.return_value = preview

        image = document.render_preview()

        document._psd.composite.assert_called_once_with(ignore_preview=True, color=0.0, alpha=0.0)
        self.assertEqual(image.mode, "RGBA")
        self.assertEqual(image.size, (2, 2))

    def test_render_preview_thumbnail_uses_existing_full_preview_path(self) -> None:
        document = PsdDocument.__new__(PsdDocument)
        preview = Image.new("RGB", (4, 2), (255, 0, 0))
        document._psd = Mock()
        document._psd.composite.return_value = preview

        image = document.render_preview_thumbnail((2, 2))

        document._psd.composite.assert_called_once_with(ignore_preview=True, color=0.0, alpha=0.0)
        self.assertEqual(image.mode, "RGBA")
        self.assertEqual(image.size, (2, 1))

    def test_render_layer_thumbnail_uses_topil_fast_path_for_pixel_layer(self) -> None:
        document = PsdDocument.__new__(PsdDocument)
        node = Mock()
        node.has_pixels.return_value = True
        node.topil.return_value = Image.new("RGB", (4, 2), (255, 0, 0))
        document.get_layer_node = Mock(return_value=node)

        image = document.render_layer_thumbnail("0", max_size=(2, 2))

        document.get_layer_node.assert_called_once_with("0")
        node.topil.assert_called_once_with(apply_icc=False)
        node.composite.assert_not_called()
        self.assertEqual(image.mode, "RGBA")
        self.assertEqual(image.size, (2, 1))

    def test_render_layer_thumbnail_falls_back_to_composite_when_topil_has_no_image(self) -> None:
        document = PsdDocument.__new__(PsdDocument)
        node = Mock()
        node.has_pixels.return_value = True
        node.topil.return_value = None
        node.composite.return_value = Image.new("RGB", (4, 2), (0, 0, 255))
        document.get_layer_node = Mock(return_value=node)

        image = document.render_layer_thumbnail("0", max_size=(2, 2))

        node.topil.assert_called_once_with(apply_icc=False)
        node.composite.assert_called_once_with()
        self.assertEqual(image.mode, "RGBA")
        self.assertEqual(image.size, (2, 1))


if __name__ == "__main__":
    unittest.main()

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


if __name__ == "__main__":
    unittest.main()

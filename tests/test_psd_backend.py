from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

from PIL import Image
from psd_tools import PSDImage
from psd_tools.constants import BlendMode as PsdBlendMode

from psd_decomposer.blend_modes import LayerBlendMode
from psd_decomposer.psd_backend import PsdDocument


WORKSPACE_DIR = Path(__file__).resolve().parents[1]


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

    def test_render_composite_filters_to_selected_layers_and_their_groups(self) -> None:
        """PSD 선택 합성은 선택 노드와 상위 그룹만 psd-tools 필터에 포함합니다."""

        document = PsdDocument.__new__(PsdDocument)
        document._psd = Mock()
        document._psd.composite.return_value = Image.new("RGB", (2, 2), (255, 0, 0))
        group = Mock()
        group.parent = document._psd
        selected_node = Mock()
        selected_node.parent = group
        unrelated_node = Mock()
        document.get_layer_node = Mock(return_value=selected_node)

        image = document.render_composite(("0",))

        kwargs = document._psd.composite.call_args.kwargs
        layer_filter = kwargs.pop("layer_filter")
        self.assertEqual(kwargs, {"ignore_preview": True, "color": 0.0, "alpha": 0.0})
        self.assertTrue(layer_filter(selected_node))
        self.assertTrue(layer_filter(group))
        self.assertFalse(layer_filter(unrelated_node))
        self.assertEqual(image.mode, "RGBA")

    def test_render_layer_for_png_bakes_psd_blend_mode_against_lower_layers(self) -> None:
        """PSD 개별 PNG용 렌더링은 실제 하위 레이어 합성 결과로 특수 모드 색을 보정합니다."""

        source_path = WORKSPACE_DIR / f"test-psd-normal-equivalent-{uuid4().hex}.psd"
        try:
            psd = PSDImage.new("RGBA", (1, 1), (0, 0, 0, 0))
            psd.create_pixel_layer(Image.new("RGBA", (1, 1), (128, 128, 128, 255)), name="Bottom")
            top = psd.create_pixel_layer(Image.new("RGBA", (1, 1), (128, 255, 255, 255)), name="Top")
            top.blend_mode = PsdBlendMode.MULTIPLY
            psd.save(source_path)
            document = PsdDocument(source_path)
            top_layer = next(layer for layer in document.layers if layer.name == "Top")

            image = document.render_layer_for_png(top_layer.id)
        finally:
            source_path.unlink(missing_ok=True)

        self.assertEqual(top_layer.blend_mode, LayerBlendMode.MULTIPLY)
        self.assertEqual(image.getpixel((0, 0)), (64, 128, 128, 255))

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

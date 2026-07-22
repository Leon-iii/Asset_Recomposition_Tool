from __future__ import annotations

import unittest

from PIL import Image

from psd_decomposer.blend_modes import (
    LayerBlendMode,
    blend_mode_display_name,
    blend_mode_from_aseprite,
    blend_mode_from_psd,
    blend_mode_to_aseprite,
    blend_mode_to_psd,
    composite_layer,
    normal_equivalent_layer,
)


class BlendModeMappingTests(unittest.TestCase):
    def test_aseprite_multiply_and_addition_values_round_trip(self) -> None:
        """Aseprite의 곱하기와 더하기 모드 숫자를 공통 모델과 양방향 변환합니다."""

        self.assertEqual(blend_mode_from_aseprite(1), LayerBlendMode.MULTIPLY)
        self.assertEqual(blend_mode_to_aseprite(LayerBlendMode.MULTIPLY), 1)
        self.assertEqual(blend_mode_from_aseprite(16), LayerBlendMode.ADDITION)
        self.assertEqual(blend_mode_to_aseprite(LayerBlendMode.ADDITION), 16)

    def test_psd_linear_dodge_maps_to_common_addition_mode(self) -> None:
        """PSD Linear Dodge 키를 공통 더하기 모드로 정규화합니다."""

        self.assertEqual(blend_mode_from_psd(b"lddg"), LayerBlendMode.ADDITION)
        self.assertEqual(blend_mode_to_psd(LayerBlendMode.ADDITION), b"lddg")

    def test_psd_only_mode_has_no_aseprite_value(self) -> None:
        """Aseprite에 없는 PSD 전용 모드는 변환 가능한 숫자를 반환하지 않습니다."""

        self.assertIsNone(blend_mode_to_aseprite(LayerBlendMode.VIVID_LIGHT))

    def test_blend_mode_has_korean_layer_table_name(self) -> None:
        """레이어 테이블에 표시할 공통 블렌드 모드의 한글 이름을 반환합니다."""

        self.assertEqual(blend_mode_display_name(LayerBlendMode.MULTIPLY), "곱하기")
        self.assertEqual(blend_mode_display_name(LayerBlendMode.ADDITION), "더하기")


class BlendModeCompositeTests(unittest.TestCase):
    def test_multiply_blends_opaque_rgba_pixels(self) -> None:
        """불투명 픽셀 두 개를 곱하기 모드로 합성한 RGB 결과를 검증합니다."""

        backdrop = Image.new("RGBA", (1, 1), (128, 128, 128, 255))
        source = Image.new("RGBA", (1, 1), (128, 255, 255, 255))

        result = composite_layer(backdrop, source, (0, 0), LayerBlendMode.MULTIPLY)

        self.assertEqual(result.getpixel((0, 0)), (64, 128, 128, 255))

    def test_layer_outside_canvas_is_ignored(self) -> None:
        """캔버스와 겹치지 않는 레이어는 원본 캔버스를 변경하지 않습니다."""

        backdrop = Image.new("RGBA", (1, 1), (10, 20, 30, 255))
        source = Image.new("RGBA", (1, 1), (255, 255, 255, 255))

        result = composite_layer(backdrop, source, (2, 2), LayerBlendMode.SCREEN)

        self.assertEqual(result.getpixel((0, 0)), (10, 20, 30, 255))

    def test_normal_equivalent_layer_matches_original_blend_on_same_backdrop(self) -> None:
        """보정 PNG를 같은 배경에 Normal로 합성하면 원본 특수 모드 결과와 일치합니다."""

        backdrop = Image.new("RGBA", (1, 1), (128, 128, 128, 255))
        source = Image.new("RGBA", (1, 1), (128, 255, 255, 192))

        equivalent = normal_equivalent_layer(backdrop, source, (0, 0), LayerBlendMode.MULTIPLY)
        original_result = composite_layer(backdrop, source, (0, 0), LayerBlendMode.MULTIPLY)
        normal_result = composite_layer(backdrop, equivalent, (0, 0), LayerBlendMode.NORMAL)

        self.assertEqual(equivalent.getpixel((0, 0))[3], 192)
        self.assertTrue(
            all(abs(original - normal) <= 1 for original, normal in zip(original_result.getpixel((0, 0)), normal_result.getpixel((0, 0))))
        )


if __name__ == "__main__":
    unittest.main()

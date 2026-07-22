from __future__ import annotations

import unittest

from psd_decomposer.blend_modes import LayerBlendMode
from psd_decomposer.document_backend import DocumentFormat
from psd_decomposer.gui import (
    build_drop_detail_text,
    find_unsupported_aseprite_blend_mode_layers,
    resolve_blend_mode_control_state,
    resolve_export_button_state,
    resolve_export_format_state,
    should_warn_aseprite_multiframe,
    should_warn_psd_rasterization,
    should_suppress_image_worker_progress,
)
from psd_decomposer.models import LayerInfo


class GuiStateTests(unittest.TestCase):
    def test_no_loaded_document_disables_psd_and_forces_png(self) -> None:
        state = resolve_export_format_state(
            document_format=None,
            current_format="PSD",
        )

        self.assertEqual(state.format_value, "PNG")
        self.assertFalse(state.psd_enabled)
        self.assertFalse(state.ase_enabled)

    def test_psd_document_keeps_psd_format_and_enables_psd(self) -> None:
        state = resolve_export_format_state(
            document_format=DocumentFormat.PSD,
            current_format="PSD",
        )

        self.assertEqual(state.format_value, "PSD")
        self.assertTrue(state.psd_enabled)
        self.assertTrue(state.ase_enabled)

    def test_psd_document_keeps_ase_format(self) -> None:
        state = resolve_export_format_state(
            document_format=DocumentFormat.PSD,
            current_format="ASE",
        )

        self.assertEqual(state.format_value, "ASE")
        self.assertTrue(state.psd_enabled)
        self.assertTrue(state.ase_enabled)

    def test_psd_document_with_invalid_current_format_falls_back_to_png(self) -> None:
        state = resolve_export_format_state(
            document_format=DocumentFormat.PSD,
            current_format="TIFF",
        )

        self.assertEqual(state.format_value, "PNG")
        self.assertTrue(state.psd_enabled)
        self.assertTrue(state.ase_enabled)

    def test_aseprite_document_keeps_psd_format_and_enables_psd(self) -> None:
        state = resolve_export_format_state(
            document_format=DocumentFormat.ASEPRITE,
            current_format="PSD",
        )

        self.assertEqual(state.format_value, "PSD")
        self.assertTrue(state.psd_enabled)
        self.assertTrue(state.ase_enabled)

    def test_aseprite_document_keeps_ase_format(self) -> None:
        state = resolve_export_format_state(
            document_format=DocumentFormat.ASEPRITE,
            current_format="ASE",
        )

        self.assertEqual(state.format_value, "ASE")
        self.assertTrue(state.psd_enabled)
        self.assertTrue(state.ase_enabled)

    def test_psd_rasterization_warning_only_applies_to_psd_source_and_psd_output(self) -> None:
        self.assertTrue(should_warn_psd_rasterization(DocumentFormat.PSD, "PSD"))
        self.assertFalse(should_warn_psd_rasterization(DocumentFormat.PSD, "PNG"))
        self.assertFalse(should_warn_psd_rasterization(DocumentFormat.PSD, "ASE"))
        self.assertFalse(should_warn_psd_rasterization(DocumentFormat.ASEPRITE, "PSD"))
        self.assertFalse(should_warn_psd_rasterization(None, "PSD"))

    def test_aseprite_multiframe_warning_only_applies_to_aseprite_with_multiple_frames(self) -> None:
        self.assertTrue(should_warn_aseprite_multiframe(DocumentFormat.ASEPRITE, 2))
        self.assertTrue(should_warn_aseprite_multiframe(DocumentFormat.ASEPRITE, 3))
        self.assertFalse(should_warn_aseprite_multiframe(DocumentFormat.ASEPRITE, 1))
        self.assertFalse(should_warn_aseprite_multiframe(DocumentFormat.PSD, 2))
        self.assertFalse(should_warn_aseprite_multiframe(None, 2))

    def test_find_unsupported_aseprite_blend_modes_uses_selected_layers_only(self) -> None:
        """ASE 변환 경고 목록에는 선택된 PSD 전용 블렌드 모드 레이어만 포함합니다."""

        layers = (
            LayerInfo("0", "Multiply", (), True, 1, 1, blend_mode=LayerBlendMode.MULTIPLY),
            LayerInfo("1", "Vivid", (), True, 1, 1, blend_mode=LayerBlendMode.VIVID_LIGHT),
            LayerInfo("2", "Linear", (), True, 1, 1, blend_mode=LayerBlendMode.LINEAR_LIGHT),
        )

        unsupported = find_unsupported_aseprite_blend_mode_layers(layers, ("0", "1"))

        self.assertEqual([layer.id for layer in unsupported], ["1"])

    def test_image_worker_progress_is_suppressed_while_exporting(self) -> None:
        self.assertTrue(should_suppress_image_worker_progress(True))
        self.assertFalse(should_suppress_image_worker_progress(False))

    def test_blend_mode_controls_only_enable_for_decomposed_png(self) -> None:
        """블렌드 모드 정책은 분해 모드와 PNG 출력이 함께 선택된 경우에만 활성화됩니다."""

        self.assertEqual(resolve_blend_mode_control_state("decompose", "PNG"), "normal")
        self.assertEqual(resolve_blend_mode_control_state("reconstruct", "PNG"), "disabled")
        self.assertEqual(resolve_blend_mode_control_state("decompose", "PSD"), "disabled")
        self.assertEqual(resolve_blend_mode_control_state("decompose", "ASE"), "disabled")

    def test_export_button_is_disabled_while_exporting(self) -> None:
        """선택된 레이어가 있어도 내보내기 중에는 실행 버튼을 비활성화합니다."""

        self.assertEqual(resolve_export_button_state(1, True), "disabled")
        self.assertEqual(resolve_export_button_state(1, False), "normal")
        self.assertEqual(resolve_export_button_state(0, False), "disabled")

    def test_drop_detail_text_includes_canvas_size_and_frame_count(self) -> None:
        detail_text = build_drop_detail_text(24, 16, 3)

        self.assertEqual(detail_text, "캔버스 크기: 24x16 px\n총 프레임 수: 3")

    def test_aseprite_document_with_invalid_current_format_falls_back_to_png(self) -> None:
        state = resolve_export_format_state(
            document_format=DocumentFormat.ASEPRITE,
            current_format="TIFF",
        )

        self.assertEqual(state.format_value, "PNG")
        self.assertTrue(state.psd_enabled)
        self.assertTrue(state.ase_enabled)


if __name__ == "__main__":
    unittest.main()

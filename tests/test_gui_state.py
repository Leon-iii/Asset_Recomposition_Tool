from __future__ import annotations

import unittest

from psd_decomposer.document_backend import DocumentFormat
from psd_decomposer.gui import build_drop_detail_text, resolve_export_format_state


class GuiStateTests(unittest.TestCase):
    def test_no_loaded_document_disables_psd_and_forces_png(self) -> None:
        state = resolve_export_format_state(
            document_format=None,
            psd_export_available=True,
            psd_export_message="PSD 저장 가능",
            current_format="PSD",
        )

        self.assertEqual(state.format_value, "PNG")
        self.assertFalse(state.psd_enabled)
        self.assertFalse(state.ase_enabled)
        self.assertIn("PSD 원본 파일을 먼저 로드", state.warning_message)

    def test_psd_document_with_available_com_keeps_current_valid_format_and_enables_psd(self) -> None:
        state = resolve_export_format_state(
            document_format=DocumentFormat.PSD,
            psd_export_available=True,
            psd_export_message="PSD 저장 가능",
            current_format="PSD",
        )

        self.assertEqual(state.format_value, "PSD")
        self.assertTrue(state.psd_enabled)
        self.assertFalse(state.ase_enabled)
        self.assertEqual(state.warning_message, "PSD 저장 가능")

    def test_psd_document_without_available_com_forces_png_and_uses_com_warning(self) -> None:
        state = resolve_export_format_state(
            document_format=DocumentFormat.PSD,
            psd_export_available=False,
            psd_export_message="Photoshop COM 등록을 찾을 수 없습니다.",
            current_format="PSD",
        )

        self.assertEqual(state.format_value, "PNG")
        self.assertFalse(state.psd_enabled)
        self.assertFalse(state.ase_enabled)
        self.assertEqual(state.warning_message, "Photoshop COM 등록을 찾을 수 없습니다.")

    def test_aseprite_document_forces_png_even_when_com_is_available(self) -> None:
        state = resolve_export_format_state(
            document_format=DocumentFormat.ASEPRITE,
            psd_export_available=True,
            psd_export_message="PSD 저장 가능",
            current_format="PSD",
        )

        self.assertEqual(state.format_value, "PNG")
        self.assertFalse(state.psd_enabled)
        self.assertTrue(state.ase_enabled)
        self.assertIn("PSD 원본 파일에서만", state.warning_message)

    def test_psd_document_with_invalid_current_format_falls_back_to_png(self) -> None:
        state = resolve_export_format_state(
            document_format=DocumentFormat.PSD,
            psd_export_available=True,
            psd_export_message="PSD 저장 가능",
            current_format="TIFF",
        )

        self.assertEqual(state.format_value, "PNG")
        self.assertTrue(state.psd_enabled)
        self.assertFalse(state.ase_enabled)

    def test_aseprite_document_keeps_ase_format(self) -> None:
        state = resolve_export_format_state(
            document_format=DocumentFormat.ASEPRITE,
            psd_export_available=True,
            psd_export_message="PSD 저장 가능",
            current_format="ASE",
        )

        self.assertEqual(state.format_value, "ASE")
        self.assertFalse(state.psd_enabled)
        self.assertTrue(state.ase_enabled)

    def test_drop_detail_text_includes_canvas_size_and_frame_count(self) -> None:
        detail_text = build_drop_detail_text(24, 16, 3)

        self.assertEqual(detail_text, "캔버스 크기: 24x16 px\n총 프레임 수: 3")


if __name__ == "__main__":
    unittest.main()

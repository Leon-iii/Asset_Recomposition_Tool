from __future__ import annotations

import unittest
from pathlib import Path
from uuid import uuid4

from psd_decomposer.config import AppSettings


WORKSPACE_DIR = Path(__file__).resolve().parents[1]


class AppSettingsTests(unittest.TestCase):
    def test_legacy_settings_default_to_preserving_blend_result(self) -> None:
        """새 정책 필드가 없는 이전 설정 파일에는 혼합 결과 유지 기본값을 적용합니다."""

        settings_path = WORKSPACE_DIR / f"test-settings-{uuid4().hex}.json"
        try:
            settings_path.write_text('{"output_mode": "decompose", "export_format": "PNG"}', encoding="utf-8")

            settings = AppSettings.load(settings_path)
        finally:
            settings_path.unlink(missing_ok=True)

        self.assertEqual(settings.png_blend_mode_policy, "preserve_result")

    def test_invalid_blend_mode_policy_falls_back_to_preserving_result(self) -> None:
        """알 수 없는 PNG 블렌드 정책은 안전한 혼합 결과 유지 값으로 복구합니다."""

        settings_path = WORKSPACE_DIR / f"test-invalid-settings-{uuid4().hex}.json"
        try:
            settings_path.write_text('{"png_blend_mode_policy": "invalid"}', encoding="utf-8")

            settings = AppSettings.load(settings_path)
        finally:
            settings_path.unlink(missing_ok=True)

        self.assertEqual(settings.png_blend_mode_policy, "preserve_result")


if __name__ == "__main__":
    unittest.main()

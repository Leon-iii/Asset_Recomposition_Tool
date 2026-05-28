from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from psd_decomposer.models import ExportJob, LayerInfo
from psd_decomposer.naming import (
    build_base_name,
    build_output_directory,
    build_reconstructed_base_name,
    resolve_output_path,
    sanitize_filename_part,
    unique_output_path,
)


class NamingTests(unittest.TestCase):
    def make_job(self, **overrides) -> ExportJob:
        values = {
            "source_path": Path("C:/work/City1.psd"),
            "output_directory": Path("C:/out"),
            "wrap_with_folder": True,
            "include_original_name": True,
            "include_layer_name": True,
            "include_date": True,
            "overwrite_existing": False,
            "export_format": "PNG",
            "rescale": 100,
            "preserve_canvas": True,
            "selected_layer_ids": ("0",),
        }
        values.update(overrides)
        return ExportJob(**values)

    def test_build_base_name_concatenates_enabled_parts(self) -> None:
        layer = LayerInfo(id="0", name="sky", path=(), visible=True, width=10, height=20)
        self.assertEqual(build_base_name(self.make_job(), layer, date(2026, 5, 7)), "City1_sky_260507")

    def test_layer_name_is_fallback_when_all_name_parts_disabled(self) -> None:
        layer = LayerInfo(id="0", name="background", path=(), visible=True, width=10, height=20)
        job = self.make_job(include_original_name=False, include_layer_name=False, include_date=False)
        self.assertEqual(build_base_name(job, layer, date(2026, 5, 7)), "background")

    def test_wrap_directory_uses_source_name(self) -> None:
        self.assertEqual(build_output_directory(self.make_job()), Path("C:/out/City1_decomposed"))

    def test_reconstructed_base_name_uses_top_layer_and_active_count(self) -> None:
        job = self.make_job(include_original_name=False, include_layer_name=True, include_layer_count=True, include_date=False)

        self.assertEqual(build_reconstructed_base_name(job, "Group", 3, date(2026, 5, 7)), "Group_3_Layers")

    def test_reconstructed_base_name_sanitizes_top_layer_name(self) -> None:
        job = self.make_job(include_original_name=False, include_layer_name=True, include_layer_count=True, include_date=False)

        self.assertEqual(build_reconstructed_base_name(job, "bad:name*", 2, date(2026, 5, 7)), "bad_name__2_Layers")

    def test_reconstructed_base_name_uses_enabled_file_name_parts(self) -> None:
        job = self.make_job(include_original_name=True, include_layer_name=True, include_layer_count=True, include_date=True)

        self.assertEqual(build_reconstructed_base_name(job, "Group", 3, date(2026, 5, 7)), "City1_Group_3_Layers_260507")

    def test_reconstructed_base_name_falls_back_to_top_layer_name(self) -> None:
        job = self.make_job(include_original_name=False, include_layer_name=False, include_layer_count=False, include_date=False)

        self.assertEqual(build_reconstructed_base_name(job, "Group", 3, date(2026, 5, 7)), "Group")

    def test_sanitize_filename_part_removes_invalid_characters(self) -> None:
        self.assertEqual(sanitize_filename_part('bad:name*'), "bad_name_")

    def test_unique_output_path_adds_numeric_suffix(self) -> None:
        directory = Path("C:/out")

        def fake_exists(path: Path) -> bool:
            return path.name == "City1.png"

        with patch.object(Path, "exists", fake_exists):
            self.assertEqual(unique_output_path(directory, "City1", "png").name, "City1_2.png")

    def test_resolve_output_path_overwrites_existing_but_not_reserved_path(self) -> None:
        directory = Path("C:/out")
        reserved = {directory / "City1.png"}

        def fake_exists(path: Path) -> bool:
            return path.name in {"City1.png", "City1_2.png"}

        with patch.object(Path, "exists", fake_exists):
            self.assertEqual(
                resolve_output_path(directory, "City1", "png", overwrite_existing=True, reserved_paths=reserved).name,
                "City1_2.png",
            )


if __name__ == "__main__":
    unittest.main()

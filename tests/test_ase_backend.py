from __future__ import annotations

import unittest
from pathlib import Path
from uuid import uuid4

from psd_decomposer.ase_backend import AsepriteDocument
from psd_decomposer.aseprite_codec import decode_aseprite_file
from psd_decomposer.blend_modes import LayerBlendMode
from psd_decomposer.document_backend import DocumentBackendError, DocumentFormat, load_document
from tests.ase_fixtures import make_aseprite_bytes, make_cel_chunk, make_frame, make_header, make_layer_chunk, make_raw_cel_payload

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

    def test_render_preview_applies_aseprite_layer_blend_mode(self) -> None:
        """Aseprite 레이어 모드를 수집하고 첫 프레임 미리보기 합성에 적용합니다."""

        source_path = WORKSPACE_DIR / f"test-ase-blend-{uuid4().hex}.aseprite"
        try:
            source_path.write_bytes(_blend_mode_aseprite_bytes())
            document = AsepriteDocument(source_path)

            image = document.render_preview()
        finally:
            source_path.unlink(missing_ok=True)

        self.assertEqual(document.layers[1].blend_mode, LayerBlendMode.MULTIPLY)
        self.assertEqual(image.getpixel((0, 0)), (64, 128, 128, 255))

    def test_render_composite_uses_only_selected_aseprite_layers(self) -> None:
        """선택 합성은 원본 visibility와 별개로 전달받은 레이어만 렌더링합니다."""

        source_path = WORKSPACE_DIR / f"test-ase-selected-blend-{uuid4().hex}.aseprite"
        try:
            source_path.write_bytes(_blend_mode_aseprite_bytes())
            document = AsepriteDocument(source_path)

            image = document.render_composite(("0",))
        finally:
            source_path.unlink(missing_ok=True)

        self.assertEqual(image.getpixel((0, 0)), (128, 128, 128, 255))

    def test_render_layer_for_png_bakes_blend_mode_against_lower_layers(self) -> None:
        """ASE 개별 PNG용 렌더링은 하위 레이어를 배경으로 특수 모드 색을 보정합니다."""

        source_path = WORKSPACE_DIR / f"test-ase-normal-equivalent-{uuid4().hex}.aseprite"
        try:
            source_path.write_bytes(_blend_mode_aseprite_bytes())
            document = AsepriteDocument(source_path)

            image = document.render_layer_for_png("1")
        finally:
            source_path.unlink(missing_ok=True)

        self.assertEqual(image.getpixel((0, 0)), (64, 128, 128, 255))

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


def _blend_mode_aseprite_bytes() -> bytes:
    """1픽셀 곱하기 합성 검증용 두 레이어 Aseprite 바이트를 생성합니다."""

    # 아래 Normal 회색 레이어 위에 Multiply 청록 레이어가 놓이는 한 프레임 문서를 만듭니다.
    frames = [
        make_frame(
            chunks=[
                make_layer_chunk(name="Bottom", blend_mode=0),
                make_layer_chunk(name="Multiply", blend_mode=1),
                make_cel_chunk(make_raw_cel_payload(layer_index=0, pixels=bytes([128, 128, 128, 255]))),
                make_cel_chunk(make_raw_cel_payload(layer_index=1, pixels=bytes([128, 255, 255, 255]))),
            ]
        )
    ]
    body_size = sum(len(frame) for frame in frames)
    return make_aseprite_bytes(
        header=make_header(file_size=128 + body_size, frames=1, width=1, height=1),
        frames=frames,
    )


if __name__ == "__main__":
    unittest.main()

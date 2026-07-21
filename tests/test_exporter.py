from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from PIL import Image
from psd_tools import PSDImage

from psd_decomposer.aseprite_codec import decode_aseprite_file
from psd_decomposer.document_backend import DocumentBackendError, DocumentFormat
from psd_decomposer.exporter import Exporter
from psd_decomposer.models import ExportJob, LayerInfo
from tests.ase_fixtures import make_aseprite_bytes, make_cel_chunk, make_frame, make_header, make_layer_chunk, make_raw_cel_payload


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "aseprite"
WORKSPACE_DIR = Path(__file__).resolve().parents[1]


class FakeDocument:
    format = DocumentFormat.PSD
    width = 6
    height = 5

    def __init__(self, layer: LayerInfo, image: Image.Image, *additional_layers: tuple[LayerInfo, Image.Image]) -> None:
        self.layer = layer
        self.image = image
        self._images_by_id = {layer.id: image}
        self.layers = (layer,)
        if additional_layers:
            layers = [layer]
            for additional_layer, additional_image in additional_layers:
                layers.append(additional_layer)
                self._images_by_id[additional_layer.id] = additional_image
            self.layers = tuple(layers)

    def get_layer_info(self, layer_id: str) -> LayerInfo:
        for layer in self.layers:
            if layer.id == layer_id:
                return layer
        raise DocumentBackendError(f"레이어 ID를 찾을 수 없습니다: {layer_id}")

    def render_layer(self, layer_id: str) -> Image.Image:
        return self._images_by_id[layer_id]


class ExporterImageTests(unittest.TestCase):
    def test_prepare_png_image_preserves_canvas_and_position(self) -> None:
        layer = LayerInfo(id="0", name="box", path=(), visible=True, width=2, height=2, left=3, top=1)
        layer_image = Image.new("RGBA", (2, 2), (255, 0, 0, 255))
        output = Exporter._prepare_png_image(FakeDocument(layer, layer_image), "0", preserve_canvas=True)

        self.assertEqual(output.size, (6, 5))
        self.assertEqual(output.getpixel((3, 1)), (255, 0, 0, 255))
        self.assertEqual(output.getpixel((2, 1)), (0, 0, 0, 0))

    def test_prepare_png_image_can_crop_to_layer_object(self) -> None:
        layer = LayerInfo(id="0", name="box", path=(), visible=True, width=2, height=2, left=3, top=1)
        layer_image = Image.new("RGBA", (2, 2), (255, 0, 0, 255))
        output = Exporter._prepare_png_image(FakeDocument(layer, layer_image), "0", preserve_canvas=False)

        self.assertEqual(output.size, (2, 2))

    def test_export_png_handles_aseprite_layer_with_preserved_canvas(self) -> None:
        job = ExportJob(
            source_path=FIXTURE_DIR / "layer_tag_palette_cel.aseprite",
            output_directory=FIXTURE_DIR,
            wrap_with_folder=False,
            include_original_name=False,
            include_layer_name=True,
            include_date=False,
            overwrite_existing=False,
            export_format="PNG",
            rescale=100,
            preserve_canvas=True,
            selected_layer_ids=("0",),
        )
        saved_images: list[Image.Image] = []

        def capture_save(image: Image.Image, _path: Path) -> None:
            saved_images.append(image.copy())

        with patch.object(Image.Image, "save", autospec=True, side_effect=capture_save):
            outputs = Exporter().export(job)

        self.assertEqual(outputs, [FIXTURE_DIR / "Sprite.png"])
        self.assertEqual(saved_images[0].size, (4, 4))
        self.assertEqual(saved_images[0].convert("RGBA").getpixel((1, 2)), (255, 0, 0, 255))

    def test_export_png_handles_aseprite_layer_cropped_to_cel(self) -> None:
        job = ExportJob(
            source_path=FIXTURE_DIR / "layer_tag_palette_cel.aseprite",
            output_directory=FIXTURE_DIR,
            wrap_with_folder=False,
            include_original_name=False,
            include_layer_name=True,
            include_date=False,
            overwrite_existing=False,
            export_format="PNG",
            rescale=100,
            preserve_canvas=False,
            selected_layer_ids=("0",),
        )
        saved_images: list[Image.Image] = []

        def capture_save(image: Image.Image, _path: Path) -> None:
            saved_images.append(image.copy())

        with patch.object(Image.Image, "save", autospec=True, side_effect=capture_save):
            outputs = Exporter().export(job)

        self.assertEqual(outputs, [FIXTURE_DIR / "Sprite.png"])
        self.assertEqual(saved_images[0].size, (1, 1))
        self.assertEqual(saved_images[0].convert("RGBA").getpixel((0, 0)), (255, 0, 0, 255))

    def test_export_png_uses_edited_psd_layer_name_for_output_file(self) -> None:
        """PSD 레이어명 편집값이 PNG 출력 파일명에 반영되는지 확인합니다."""

        output_dir = WORKSPACE_DIR / f"test-png-renamed-output-{uuid4().hex}"
        layer = LayerInfo(id="0", name="box", path=(), visible=True, width=2, height=2, left=0, top=0)
        document = FakeDocument(layer, Image.new("RGBA", (2, 2), (255, 0, 0, 255)))
        job = ExportJob(
            source_path=Path("source.psd"),
            output_directory=output_dir,
            wrap_with_folder=False,
            include_original_name=False,
            include_layer_name=True,
            include_date=False,
            overwrite_existing=False,
            export_format="PNG",
            rescale=100,
            preserve_canvas=False,
            selected_layer_ids=("0",),
            layer_names={"0": "Hero"},
        )

        def capture_save(_image: Image.Image, _path: Path) -> None:
            return None

        try:
            with (
                patch("psd_decomposer.exporter.load_document", return_value=document),
                patch.object(Image.Image, "save", autospec=True, side_effect=capture_save),
            ):
                outputs = Exporter().export(job)
        finally:
            _remove_output_dir(output_dir)

        self.assertEqual(outputs, [output_dir / "Hero.png"])

    def test_reconstruct_png_exports_selected_layers_as_one_file(self) -> None:
        output_dir = WORKSPACE_DIR / f"test-reconstruct-output-{uuid4().hex}"
        top = LayerInfo(id="0", name="top", path=("Group",), visible=True, width=2, height=2, left=0, top=0)
        bottom = LayerInfo(id="1", name="bottom", path=("Group",), visible=True, width=2, height=2, left=3, top=2)
        document = FakeDocument(
            top,
            Image.new("RGBA", (2, 2), (255, 0, 0, 255)),
            (bottom, Image.new("RGBA", (2, 2), (0, 0, 255, 255))),
        )
        job = ExportJob(
            source_path=Path("source.psd"),
            output_directory=output_dir,
            wrap_with_folder=True,
            include_original_name=False,
            include_layer_name=True,
            include_layer_count=True,
            include_date=False,
            overwrite_existing=False,
            export_format="PNG",
            output_mode="reconstruct",
            rescale=100,
            preserve_canvas=False,
            selected_layer_ids=("0", "1"),
        )
        saved_images: list[Image.Image] = []

        def capture_save(image: Image.Image, _path: Path) -> None:
            saved_images.append(image.copy())

        try:
            with (
                patch("psd_decomposer.exporter.load_document", return_value=document),
                patch.object(Image.Image, "save", autospec=True, side_effect=capture_save),
            ):
                outputs = Exporter().export(job)
        finally:
            _remove_output_dir(output_dir)

        self.assertEqual(outputs, [output_dir / "Group_2_Layers.png"])
        self.assertEqual(len(saved_images), 1)
        self.assertEqual(saved_images[0].size, (6, 5))
        self.assertEqual(saved_images[0].getpixel((0, 0)), (255, 0, 0, 255))
        self.assertEqual(saved_images[0].getpixel((3, 2)), (0, 0, 255, 255))

    def test_reconstruct_base_name_uses_topmost_selected_layer_not_selection_order(self) -> None:
        output_dir = WORKSPACE_DIR / f"test-reconstruct-name-output-{uuid4().hex}"
        bottom = LayerInfo(id="0", name="Bottom", path=("BottomGroup",), visible=True, width=1, height=1, left=0, top=0)
        top = LayerInfo(id="1", name="Top", path=("TopGroup",), visible=True, width=1, height=1, left=1, top=1)
        document = FakeDocument(
            bottom,
            Image.new("RGBA", (1, 1), (0, 0, 255, 255)),
            (top, Image.new("RGBA", (1, 1), (255, 0, 0, 255))),
        )
        job = ExportJob(
            source_path=Path("source.psd"),
            output_directory=output_dir,
            wrap_with_folder=False,
            include_original_name=False,
            include_layer_name=True,
            include_layer_count=True,
            include_date=False,
            overwrite_existing=False,
            export_format="PNG",
            output_mode="reconstruct",
            rescale=100,
            preserve_canvas=True,
            selected_layer_ids=("0", "1"),
        )

        def capture_save(_image: Image.Image, _path: Path) -> None:
            return None

        try:
            with (
                patch("psd_decomposer.exporter.load_document", return_value=document),
                patch.object(Image.Image, "save", autospec=True, side_effect=capture_save),
            ):
                outputs = Exporter().export(job)
        finally:
            _remove_output_dir(output_dir)

        self.assertEqual(outputs, [output_dir / "TopGroup_2_Layers.png"])

    def test_reconstruct_base_name_uses_edited_top_layer_name(self) -> None:
        """재구성 출력명도 선택 스택 기준 최상위 레이어의 편집명을 사용합니다."""

        output_dir = WORKSPACE_DIR / f"test-reconstruct-renamed-name-output-{uuid4().hex}"
        bottom = LayerInfo(id="0", name="Bottom", path=(), visible=True, width=1, height=1, left=0, top=0)
        top = LayerInfo(id="1", name="Top", path=(), visible=True, width=1, height=1, left=1, top=1)
        document = FakeDocument(
            bottom,
            Image.new("RGBA", (1, 1), (0, 0, 255, 255)),
            (top, Image.new("RGBA", (1, 1), (255, 0, 0, 255))),
        )
        job = ExportJob(
            source_path=Path("source.psd"),
            output_directory=output_dir,
            wrap_with_folder=False,
            include_original_name=False,
            include_layer_name=True,
            include_layer_count=True,
            include_date=False,
            overwrite_existing=False,
            export_format="PNG",
            output_mode="reconstruct",
            rescale=100,
            preserve_canvas=True,
            selected_layer_ids=("0", "1"),
            layer_names={"1": "HeroTop"},
        )

        def capture_save(_image: Image.Image, _path: Path) -> None:
            return None

        try:
            with (
                patch("psd_decomposer.exporter.load_document", return_value=document),
                patch.object(Image.Image, "save", autospec=True, side_effect=capture_save),
            ):
                outputs = Exporter().export(job)
        finally:
            _remove_output_dir(output_dir)

        self.assertEqual(outputs, [output_dir / "HeroTop_2_Layers.png"])

    def test_export_psd_rasterizes_psd_source_layer_without_photoshop(self) -> None:
        output_dir = WORKSPACE_DIR / f"test-psd-raster-output-{uuid4().hex}"
        layer = LayerInfo(id="0", name="box", path=(), visible=True, width=2, height=2, left=3, top=1)
        document = FakeDocument(layer, Image.new("RGBA", (2, 2), (255, 0, 0, 255)))
        job = ExportJob(
            source_path=Path("source.psd"),
            output_directory=output_dir,
            wrap_with_folder=False,
            include_original_name=False,
            include_layer_name=True,
            include_date=False,
            overwrite_existing=False,
            export_format="PSD",
            rescale=100,
            preserve_canvas=True,
            selected_layer_ids=("0",),
        )

        try:
            with patch("psd_decomposer.exporter.load_document", return_value=document):
                outputs = Exporter().export(job)
            psd = PSDImage.open(outputs[0])
            self.assertEqual(outputs, [output_dir / "box.psd"])
            self.assertEqual(psd.size, (6, 5))
            self.assertEqual(len(psd), 1)
            self.assertEqual(psd[0].name, "box")
            self.assertEqual(psd[0].bbox, (3, 1, 5, 3))
        finally:
            _remove_output_dir(output_dir)

    def test_export_psd_uses_edited_layer_name_for_file_and_pixel_layer(self) -> None:
        """PSD 출력 파일명과 내부 레스터 레이어 이름에 편집값을 적용합니다."""

        output_dir = WORKSPACE_DIR / f"test-psd-renamed-output-{uuid4().hex}"
        layer = LayerInfo(id="0", name="box", path=(), visible=True, width=2, height=2, left=3, top=1)
        document = FakeDocument(layer, Image.new("RGBA", (2, 2), (255, 0, 0, 255)))
        job = ExportJob(
            source_path=Path("source.psd"),
            output_directory=output_dir,
            wrap_with_folder=False,
            include_original_name=False,
            include_layer_name=True,
            include_date=False,
            overwrite_existing=False,
            export_format="PSD",
            rescale=100,
            preserve_canvas=True,
            selected_layer_ids=("0",),
            layer_names={"0": "Hero"},
        )

        try:
            with patch("psd_decomposer.exporter.load_document", return_value=document):
                outputs = Exporter().export(job)
            psd = PSDImage.open(outputs[0])
            self.assertEqual(outputs, [output_dir / "Hero.psd"])
            self.assertEqual(psd[0].name, "Hero")
        finally:
            _remove_output_dir(output_dir)

    def test_export_psd_preserves_korean_layer_name(self) -> None:
        """한글 레이어명을 Unicode 태그로 기록해 PSD 저장 오류 없이 보존합니다."""

        output_dir = WORKSPACE_DIR / f"test-psd-korean-name-output-{uuid4().hex}"
        layer = LayerInfo(id="0", name="원본", path=(), visible=True, width=2, height=2, left=0, top=0)
        document = FakeDocument(layer, Image.new("RGBA", (2, 2), (255, 0, 0, 255)))
        job = ExportJob(
            source_path=Path("source.psd"),
            output_directory=output_dir,
            wrap_with_folder=False,
            include_original_name=False,
            include_layer_name=True,
            include_date=False,
            overwrite_existing=False,
            export_format="PSD",
            rescale=100,
            preserve_canvas=True,
            selected_layer_ids=("0",),
            layer_names={"0": "캐릭터"},
        )

        try:
            with patch("psd_decomposer.exporter.load_document", return_value=document):
                outputs = Exporter().export(job)
            psd = PSDImage.open(outputs[0])
            self.assertEqual(outputs, [output_dir / "캐릭터.psd"])
            self.assertEqual(psd[0].name, "캐릭터")
        finally:
            _remove_output_dir(output_dir)

    def test_export_psd_converts_aseprite_first_frame_layer(self) -> None:
        source_path = WORKSPACE_DIR / f"test-ase-to-psd-source-{uuid4().hex}.aseprite"
        output_dir = WORKSPACE_DIR / f"test-ase-to-psd-output-{uuid4().hex}"
        try:
            source_path.write_bytes(_multi_frame_aseprite_bytes())
            job = ExportJob(
                source_path=source_path,
                output_directory=output_dir,
                wrap_with_folder=False,
                include_original_name=False,
                include_layer_name=True,
                include_date=False,
                overwrite_existing=False,
                export_format="PSD",
                rescale=100,
                preserve_canvas=True,
                selected_layer_ids=("0",),
            )

            outputs = Exporter().export(job)
            psd = PSDImage.open(outputs[0])
            layer_image = psd[0].composite()

            self.assertEqual(outputs, [output_dir / "Sprite.psd"])
            self.assertEqual(psd.size, (2, 2))
            self.assertEqual(len(psd), 1)
            self.assertEqual(psd[0].name, "Sprite")
            self.assertEqual(layer_image.getpixel((0, 0)), (255, 0, 0, 255))
        finally:
            source_path.unlink(missing_ok=True)
            _remove_output_dir(output_dir)

    def test_reconstruct_psd_converts_aseprite_selected_layers(self) -> None:
        source_path = WORKSPACE_DIR / f"test-ase-reconstruct-psd-source-{uuid4().hex}.aseprite"
        output_dir = WORKSPACE_DIR / f"test-ase-reconstruct-psd-output-{uuid4().hex}"
        try:
            source_path.write_bytes(_two_layer_aseprite_bytes())
            job = ExportJob(
                source_path=source_path,
                output_directory=output_dir,
                wrap_with_folder=False,
                include_original_name=False,
                include_layer_name=True,
                include_layer_count=True,
                include_date=False,
                overwrite_existing=False,
                export_format="PSD",
                output_mode="reconstruct",
                rescale=100,
                preserve_canvas=True,
                selected_layer_ids=("0", "1"),
            )

            outputs = Exporter().export(job)
            psd = PSDImage.open(outputs[0])

            self.assertEqual(outputs, [output_dir / "Bottom_2_Layers.psd"])
            self.assertEqual(len(psd), 2)
            self.assertEqual([layer.name for layer in psd], ["Top", "Bottom"])
        finally:
            source_path.unlink(missing_ok=True)
            _remove_output_dir(output_dir)

    def test_export_ase_converts_psd_layer_with_preserved_position(self) -> None:
        output_dir = WORKSPACE_DIR / f"test-psd-to-ase-output-{uuid4().hex}"
        layer = LayerInfo(id="0", name="box", path=(), visible=True, width=2, height=2, left=3, top=1)
        document = FakeDocument(layer, Image.new("RGBA", (2, 2), (255, 0, 0, 255)))
        job = ExportJob(
            source_path=Path("source.psd"),
            output_directory=output_dir,
            wrap_with_folder=False,
            include_original_name=False,
            include_layer_name=True,
            include_date=False,
            overwrite_existing=False,
            export_format="ASE",
            rescale=100,
            preserve_canvas=True,
            selected_layer_ids=("0",),
        )

        try:
            with patch("psd_decomposer.exporter.load_document", return_value=document):
                outputs = Exporter().export(job)
            decoded = decode_aseprite_file(outputs[0])
        finally:
            _remove_output_dir(output_dir)

        self.assertEqual(outputs, [output_dir / "box.aseprite"])
        self.assertEqual((decoded.header.width, decoded.header.height), (6, 5))
        self.assertEqual(len(decoded.frames), 1)
        self.assertEqual([layer.name for layer in decoded.layers], ["box"])
        self.assertEqual((decoded.frames[0].cels[0].x, decoded.frames[0].cels[0].y), (3, 1))
        self.assertEqual(decoded.frames[0].cels[0].pixels, bytes([255, 0, 0, 255]) * 4)

    def test_export_ase_uses_edited_layer_name_for_file_and_layer_chunk(self) -> None:
        """PSD에서 ASE로 변환할 때 파일명과 LayerChunk 이름에 편집값을 적용합니다."""

        output_dir = WORKSPACE_DIR / f"test-psd-renamed-ase-output-{uuid4().hex}"
        layer = LayerInfo(id="0", name="box", path=(), visible=True, width=2, height=2, left=3, top=1)
        document = FakeDocument(layer, Image.new("RGBA", (2, 2), (255, 0, 0, 255)))
        job = ExportJob(
            source_path=Path("source.psd"),
            output_directory=output_dir,
            wrap_with_folder=False,
            include_original_name=False,
            include_layer_name=True,
            include_date=False,
            overwrite_existing=False,
            export_format="ASE",
            rescale=100,
            preserve_canvas=True,
            selected_layer_ids=("0",),
            layer_names={"0": "Hero"},
        )

        try:
            with patch("psd_decomposer.exporter.load_document", return_value=document):
                outputs = Exporter().export(job)
            decoded = decode_aseprite_file(outputs[0])
        finally:
            _remove_output_dir(output_dir)

        self.assertEqual(outputs, [output_dir / "Hero.aseprite"])
        self.assertEqual([layer.name for layer in decoded.layers], ["Hero"])

    def test_reconstruct_ase_converts_psd_selected_layers(self) -> None:
        output_dir = WORKSPACE_DIR / f"test-psd-reconstruct-ase-output-{uuid4().hex}"
        bottom = LayerInfo(id="0", name="Bottom", path=(), visible=True, width=1, height=1, left=0, top=0)
        top = LayerInfo(id="1", name="Top", path=(), visible=True, width=1, height=1, left=2, top=2)
        document = FakeDocument(
            bottom,
            Image.new("RGBA", (1, 1), (0, 0, 255, 255)),
            (top, Image.new("RGBA", (1, 1), (255, 0, 0, 255))),
        )
        job = ExportJob(
            source_path=Path("source.psd"),
            output_directory=output_dir,
            wrap_with_folder=False,
            include_original_name=False,
            include_layer_name=True,
            include_layer_count=True,
            include_date=False,
            overwrite_existing=False,
            export_format="ASE",
            output_mode="reconstruct",
            rescale=100,
            preserve_canvas=True,
            selected_layer_ids=("0", "1"),
        )

        try:
            with patch("psd_decomposer.exporter.load_document", return_value=document):
                outputs = Exporter().export(job)
            decoded = decode_aseprite_file(outputs[0])
        finally:
            _remove_output_dir(output_dir)

        self.assertEqual(outputs, [output_dir / "Top_2_Layers.aseprite"])
        self.assertEqual((decoded.header.width, decoded.header.height), (6, 5))
        self.assertEqual([layer.name for layer in decoded.layers], ["Bottom", "Top"])
        self.assertEqual([cel.layer_index for cel in decoded.frames[0].cels], [0, 1])
        self.assertEqual((decoded.frames[0].cels[1].x, decoded.frames[0].cels[1].y), (2, 2))

    def test_export_ase_removes_unselected_layers_by_default(self) -> None:
        source_path = WORKSPACE_DIR / f"test-ase-source-{uuid4().hex}.aseprite"
        output_dir = WORKSPACE_DIR / f"test-ase-output-{uuid4().hex}"
        try:
            source_path.write_bytes(_two_layer_aseprite_bytes())
            job = _ase_export_job(source_path, output_dir)

            outputs = Exporter().export(job)
            decoded = decode_aseprite_file(outputs[0])

            self.assertEqual(outputs, [output_dir / "Top.aseprite"])
            self.assertEqual([layer.name for layer in decoded.layers], ["Top"])
            self.assertEqual([cel.layer_index for cel in decoded.frames[0].cels], [0])
        finally:
            source_path.unlink(missing_ok=True)
            _remove_output_dir(output_dir)


def _ase_export_job(source_path: Path, output_dir: Path) -> ExportJob:
    return ExportJob(
        source_path=source_path,
        output_directory=output_dir,
        wrap_with_folder=False,
        include_original_name=False,
        include_layer_name=True,
        include_date=False,
        overwrite_existing=False,
        export_format="ASE",
        rescale=100,
        preserve_canvas=True,
        selected_layer_ids=("0",),
    )


def _two_layer_aseprite_bytes() -> bytes:
    frames = [
        make_frame(
            chunks=[
                make_layer_chunk(name="Top"),
                make_layer_chunk(name="Bottom"),
                make_cel_chunk(make_raw_cel_payload(layer_index=0, pixels=bytes([255, 0, 0, 255]))),
                make_cel_chunk(make_raw_cel_payload(layer_index=1, pixels=bytes([0, 0, 255, 255]))),
            ]
        )
    ]
    body_size = sum(len(frame) for frame in frames)
    return make_aseprite_bytes(
        header=make_header(file_size=128 + body_size, frames=1, width=1, height=1),
        frames=frames,
    )


def _multi_frame_aseprite_bytes() -> bytes:
    frames = [
        make_frame(
            chunks=[
                make_layer_chunk(name="Sprite"),
                make_cel_chunk(make_raw_cel_payload(layer_index=0, pixels=bytes([255, 0, 0, 255]))),
            ]
        ),
        make_frame(
            chunks=[
                make_cel_chunk(make_raw_cel_payload(layer_index=0, pixels=bytes([0, 0, 255, 255]))),
            ]
        ),
    ]
    body_size = sum(len(frame) for frame in frames)
    return make_aseprite_bytes(
        header=make_header(file_size=128 + body_size, frames=2, width=2, height=2),
        frames=frames,
    )


def _remove_output_dir(output_dir: Path) -> None:
    if not output_dir.exists():
        return
    for output in output_dir.glob("*"):
        output.unlink()
    output_dir.rmdir()


if __name__ == "__main__":
    unittest.main()

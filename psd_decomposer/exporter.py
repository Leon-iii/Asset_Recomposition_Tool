from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Callable

from PIL import Image

from .aseprite_codec import keep_layers, rename_layer
from .aseprite_codec.errors import AseEditError
from .document_backend import DocumentBackend, DocumentFormat, load_document
from .models import ExportJob
from .naming import build_base_name, build_output_directory, build_reconstructed_base_name, resolve_output_path
from .psd_backend import PsdBackendError


ProgressCallback = Callable[[str], None]


class Exporter:
    """ExportJob을 실제 PNG 또는 PSD 파일로 변환하는 내보내기 서비스입니다."""

    def __init__(self, progress: ProgressCallback | None = None) -> None:
        """GUI가 넘긴 진행 콜백이 없으면 조용히 동작하도록 기본 콜백을 사용합니다."""

        self.progress = progress or (lambda _message: None)

    def export(self, job: ExportJob) -> list[Path]:
        """선택된 레이어를 요청 형식에 맞게 내보내고 생성된 파일 경로를 반환합니다."""

        if not job.selected_layer_ids:
            raise PsdBackendError("내보낼 레이어를 하나 이상 선택하세요.")
        if job.output_mode not in {"decompose", "reconstruct"}:
            raise PsdBackendError(f"지원하지 않는 작동 모드입니다: {job.output_mode}")

        document = load_document(job.source_path)
        # 재구성 모드는 단일 파일 출력이므로 하위 폴더 묶기를 항상 무시합니다.
        output_directory = job.output_directory if job.output_mode == "reconstruct" else build_output_directory(job)
        output_directory.mkdir(parents=True, exist_ok=True)

        if job.export_format == "PNG":
            if job.output_mode == "reconstruct":
                return self._export_reconstructed_png(document, job, output_directory)
            return self._export_png(document, job, output_directory)
        if job.export_format == "PSD":
            if document.format is not DocumentFormat.PSD:
                raise PsdBackendError("PSD 내보내기는 PSD 원본 파일에서만 사용할 수 있습니다.")
            if job.output_mode == "reconstruct":
                return self._export_reconstructed_psd(document, job, output_directory)
            return self._export_psd(document, job, output_directory)
        if job.export_format == "ASE":
            if document.format is not DocumentFormat.ASEPRITE:
                raise PsdBackendError("ASE 내보내기는 Aseprite 원본 파일에서만 사용할 수 있습니다.")
            return self._export_aseprite(document, job, output_directory)
        raise PsdBackendError(f"지원하지 않는 출력 형식입니다: {job.export_format}")

    def _export_png(self, document: DocumentBackend, job: ExportJob, output_directory: Path) -> list[Path]:
        """psd-tools가 렌더링한 레이어 이미지를 PNG 파일로 저장합니다."""

        outputs: list[Path] = []
        scale = job.rescale / 100
        reserved_paths: set[Path] = set()

        for layer_id in job.selected_layer_ids:
            layer = document.get_layer_info(layer_id)
            self.progress(f"PNG 렌더링 중: {layer.display_name}")
            image = self._prepare_png_image(document, layer_id, job.preserve_canvas)
            if scale != 1:
                # 확대 옵션은 캔버스 보존 또는 crop 이후의 최종 이미지 크기에 적용합니다.
                width = max(1, round(image.width * scale))
                height = max(1, round(image.height * scale))
                image = image.resize((width, height), Image.Resampling.LANCZOS)

            base_name = build_base_name(job, layer)
            output_path = resolve_output_path(
                output_directory,
                base_name,
                "png",
                job.overwrite_existing,
                reserved_paths,
            )
            image.save(output_path)
            outputs.append(output_path)

        return outputs

    def _export_reconstructed_png(self, document: DocumentBackend, job: ExportJob, output_directory: Path) -> list[Path]:
        """선택한 레이어를 하나의 PNG 이미지로 합성해 저장합니다."""

        # 선택 레이어를 원본 캔버스 기준으로 합성해 단일 이미지로 만듭니다.
        image = self._compose_selected_layers(document, job.selected_layer_ids)

        scale = job.rescale / 100
        if scale != 1:
            # 확대 옵션은 원본 캔버스 기준 합성 이미지에 적용합니다.
            width = max(1, round(image.width * scale))
            height = max(1, round(image.height * scale))
            image = image.resize((width, height), Image.Resampling.LANCZOS)

        output_path = resolve_output_path(
            output_directory,
            self._reconstructed_base_name(document, job),
            "png",
            job.overwrite_existing,
            set(),
        )
        self.progress(f"PNG 재구성 저장 중: {output_path.name}")
        image.save(output_path)
        return [output_path]

    def _compose_selected_layers(self, document: DocumentBackend, selected_layer_ids: tuple[str, ...]) -> Image.Image:
        """문서 순서를 기준으로 선택한 레이어들을 원본 캔버스 위에 합성합니다."""

        selected = set(selected_layer_ids)
        canvas = Image.new("RGBA", (document.width, document.height), (0, 0, 0, 0))
        for layer in document.layers:
            if layer.id not in selected:
                continue
            self.progress(f"레이어 합성 중: {layer.display_name}")
            layer_image = self._prepare_png_image(document, layer.id, preserve_canvas=True)
            canvas.alpha_composite(layer_image.convert("RGBA"), dest=(0, 0))
        return canvas

    @staticmethod
    def _prepare_png_image(document: DocumentBackend, layer_id: str, preserve_canvas: bool) -> Image.Image:
        """레이어를 원본 캔버스에 얹거나, 레이어 자체 크기로 crop한 이미지를 준비합니다."""

        layer = document.get_layer_info(layer_id)
        image = document.render_layer(layer_id).convert("RGBA")
        if not preserve_canvas:
            return image
        if image.size == (document.width, document.height):
            return image

        canvas = Image.new("RGBA", (document.width, document.height), (0, 0, 0, 0))
        # PSD 레이어가 캔버스 밖으로 나간 경우에도 Pillow crop/composite 범위를 안전하게 맞춥니다.
        source_left = max(0, -layer.left)
        source_top = max(0, -layer.top)
        dest_left = max(0, layer.left)
        dest_top = max(0, layer.top)
        width = min(image.width - source_left, document.width - dest_left)
        height = min(image.height - source_top, document.height - dest_top)
        if width > 0 and height > 0:
            cropped = image.crop((source_left, source_top, source_left + width, source_top + height))
            canvas.alpha_composite(cropped, dest=(dest_left, dest_top))
        return canvas

    def _export_psd(self, document: DocumentBackend, job: ExportJob, output_directory: Path) -> list[Path]:
        """Photoshop COM 자동화로 원본 PSD를 복제한 뒤 선택 레이어만 남겨 저장합니다."""

        try:
            import win32com.client
        except ImportError as exc:
            raise PsdBackendError(
                "PSD 내보내기는 Windows의 pywin32와 설치된 Photoshop이 필요합니다. "
                "PNG 내보내기는 Photoshop 없이 사용할 수 있습니다."
            ) from exc

        app = win32com.client.Dispatch("Photoshop.Application")
        outputs: list[Path] = []
        reserved_paths: set[Path] = set()

        for layer_id in job.selected_layer_ids:
            layer = document.get_layer_info(layer_id)
            base_name = build_base_name(job, layer)
            output_path = resolve_output_path(
                output_directory,
                base_name,
                "psd",
                job.overwrite_existing,
                reserved_paths,
            )
            # Photoshop 작업 전에 원본을 복사해 두어 원본 PSD는 절대 수정하지 않습니다.
            shutil.copy2(job.source_path, output_path)
            self.progress(f"PSD 준비 중: {layer.display_name}")
            self._keep_only_layer_in_photoshop(app, output_path, layer.display_name, job.rescale, job.preserve_canvas)
            outputs.append(output_path)

        return outputs

    def _export_reconstructed_psd(self, document: DocumentBackend, job: ExportJob, output_directory: Path) -> list[Path]:
        """원본 PSD를 복제한 뒤 선택한 레이어들만 남긴 단일 PSD로 저장합니다."""

        try:
            import win32com.client
        except ImportError as exc:
            raise PsdBackendError(
                "PSD 내보내기는 Windows의 pywin32와 설치된 Photoshop이 필요합니다. "
                "PNG 내보내기는 Photoshop 없이 사용할 수 있습니다."
            ) from exc

        output_path = resolve_output_path(
            output_directory,
            self._reconstructed_base_name(document, job),
            "psd",
            job.overwrite_existing,
            set(),
        )
        shutil.copy2(job.source_path, output_path)
        layer_names = [document.get_layer_info(layer_id).display_name for layer_id in job.selected_layer_ids]
        self.progress(f"PSD 재구성 중: {output_path.name}")
        app = win32com.client.Dispatch("Photoshop.Application")
        self._keep_layers_in_photoshop(app, output_path, layer_names, job.rescale, preserve_canvas=True)
        return [output_path]

    @staticmethod
    def _keep_only_layer_in_photoshop(
        app, path: Path, layer_display_name: str, rescale: int, preserve_canvas: bool
    ) -> None:
        """Photoshop JavaScript를 실행해 대상 레이어 외의 레이어를 제거하고 저장합니다."""

        Exporter._keep_layers_in_photoshop(app, path, [layer_display_name], rescale, preserve_canvas)

    @staticmethod
    def _keep_layers_in_photoshop(
        app, path: Path, layer_display_names: list[str], rescale: int, preserve_canvas: bool
    ) -> None:
        """Photoshop JavaScript를 실행해 대상 레이어 목록 외의 레이어를 제거하고 저장합니다."""

        doc = app.Open(str(path))
        try:
            target_paths_json = json.dumps(layer_display_names)
            scale = rescale / 100
            # ExtendScript는 그룹을 재귀 순회하며 경로가 선택 목록에 없는 ArtLayer를 제거합니다.
            script = f"""
var targetPaths = {target_paths_json};

function isTarget(path) {{
    for (var j = 0; j < targetPaths.length; j++) {{
        if (targetPaths[j] == path) {{
            return true;
        }}
    }}
    return false;
}}

function visit(container, ancestors) {{
    for (var i = container.layers.length - 1; i >= 0; i--) {{
        var layer = container.layers[i];
        var current = ancestors.concat([layer.name]);
        if (layer.typename == "ArtLayer") {{
            if (!isTarget(current.join(" / "))) {{
                layer.remove();
            }}
        }} else {{
            visit(layer, current);
            if (layer.layers.length == 0) {{
                layer.remove();
            }}
        }}
    }}
}}

visit(app.activeDocument, []);
if (!{json.dumps(preserve_canvas)}) {{
    app.activeDocument.trim(TrimType.TRANSPARENT, true, true, true, true);
}}
if ({scale} != 1) {{
    app.activeDocument.resizeImage(
        UnitValue(app.activeDocument.width.value * {scale}, "px"),
        UnitValue(app.activeDocument.height.value * {scale}, "px"),
        null,
        ResampleMethod.BICUBIC
    );
}}
"""
            app.DoJavaScript(script)
            doc.Save()
        finally:
            doc.Close(2)

    def _export_aseprite(self, document: DocumentBackend, job: ExportJob, output_directory: Path) -> list[Path]:
        """선택 레이어 상태를 반영한 Aseprite 문서를 .aseprite 파일로 저장합니다."""

        from .ase_backend import AsepriteDocument

        if not isinstance(document, AsepriteDocument):
            raise PsdBackendError("ASE 내보내기는 Aseprite 원본 파일에서만 사용할 수 있습니다.")

        layer_ids = set(job.selected_layer_ids)
        selected_indices = {int(layer_id) for layer_id in layer_ids}
        first_layer = document.get_layer_info(job.selected_layer_ids[0])
        base_name = (
            self._reconstructed_base_name(document, job)
            if job.output_mode == "reconstruct"
            else build_base_name(job, first_layer)
        )
        output_path = resolve_output_path(
            output_directory,
            base_name,
            "aseprite",
            job.overwrite_existing,
            set(),
        )

        ase_file = document.ase_file
        try:
            for layer_id, new_name in (job.layer_names or {}).items():
                layer_index = int(layer_id)
                if new_name and any(layer.index == layer_index and layer.name != new_name for layer in ase_file.layers):
                    ase_file = rename_layer(ase_file, layer_index, new_name)

            # 선택되지 않은 레이어는 출력 문서에서 완전히 제거합니다.
            ase_file = keep_layers(ase_file, selected_indices)
        except (AseEditError, ValueError) as exc:
            raise PsdBackendError(str(exc)) from exc

        self.progress(f"ASE 저장 중: {output_path.name}")
        export_document = AsepriteDocument(job.source_path)
        export_document.ase_file = ase_file
        export_document.save_as(output_path)
        return [output_path]

    @staticmethod
    def _reconstructed_base_name(document: DocumentBackend, job: ExportJob) -> str:
        """원본 문서 스택에서 선택된 최상위 레이어 이름과 선택 개수로 파일명을 만듭니다."""

        # 레이어 선택 순서가 아니라 문서의 스택 순서를 뒤에서부터 확인해 실제 최상위 선택 레이어를 대표로 사용합니다.
        selected_layer_ids = job.selected_layer_ids
        selected = set(selected_layer_ids)
        representative_layer = next((layer for layer in reversed(document.layers) if layer.id in selected), None)
        if representative_layer is None:
            representative_layer = document.get_layer_info(selected_layer_ids[0])
        top_layer_name = representative_layer.path[0] if representative_layer.path else representative_layer.name
        return build_reconstructed_base_name(job, top_layer_name, len(selected_layer_ids))

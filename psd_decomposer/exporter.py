from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Callable

from PIL import Image

from .aseprite_codec import keep_layers, rename_layer
from .aseprite_codec.errors import AseEditError
from .ase_writer import write_layers_to_aseprite
from .document_backend import DocumentBackend, DocumentFormat, load_document
from .models import ExportJob, LayerInfo
from .naming import build_base_name, build_output_directory, build_reconstructed_base_name, resolve_output_path
from .psd_backend import PsdBackendError
from .psd_writer import write_layers_to_psd


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
            if document.format not in {DocumentFormat.PSD, DocumentFormat.ASEPRITE}:
                raise PsdBackendError("PSD 내보내기는 PSD 또는 Aseprite 원본 파일에서만 사용할 수 있습니다.")
            if job.output_mode == "reconstruct":
                return self._export_reconstructed_document_psd(document, job, output_directory)
            return self._export_document_psd(document, job, output_directory)
        if job.export_format == "ASE":
            if job.output_mode == "reconstruct" and document.format is DocumentFormat.PSD:
                return self._export_reconstructed_document_aseprite(document, job, output_directory)
            if document.format is DocumentFormat.PSD:
                return self._export_document_aseprite(document, job, output_directory)
            if document.format is not DocumentFormat.ASEPRITE:
                raise PsdBackendError("ASE 내보내기는 PSD 또는 Aseprite 원본 파일에서만 사용할 수 있습니다.")
            return self._export_aseprite(document, job, output_directory)
        raise PsdBackendError(f"지원하지 않는 출력 형식입니다: {job.export_format}")

    def _export_png(self, document: DocumentBackend, job: ExportJob, output_directory: Path) -> list[Path]:
        """psd-tools가 렌더링한 레이어 이미지를 PNG 파일로 저장합니다."""

        outputs: list[Path] = []
        scale = job.rescale / 100
        reserved_paths: set[Path] = set()

        for layer_id in job.selected_layer_ids:
            layer = self._job_layer(document, job, layer_id)
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
        """기존 호출 호환을 위해 PSD 레스터 변환 경로로 위임합니다."""

        # PSD 원본도 Photoshop 객체를 보존하지 않고 렌더링된 픽셀 레이어 PSD로 저장합니다.
        return self._export_document_psd(document, job, output_directory)

    def _export_document_psd(self, document: DocumentBackend, job: ExportJob, output_directory: Path) -> list[Path]:
        """문서 백엔드의 렌더링 결과를 새 레스터 PSD 파일들로 변환해 저장합니다."""

        outputs: list[Path] = []
        reserved_paths: set[Path] = set()

        for layer_id in job.selected_layer_ids:
            layer = self._job_layer(document, job, layer_id)
            base_name = build_base_name(job, layer)
            output_path = resolve_output_path(
                output_directory,
                base_name,
                "psd",
                job.overwrite_existing,
                reserved_paths,
            )
            self.progress(f"PSD 변환 중: {layer.display_name}")
            write_layers_to_psd(
                document,
                (layer_id,),
                output_path,
                preserve_canvas=job.preserve_canvas,
                rescale=job.rescale,
                layer_names=job.layer_names,
            )
            outputs.append(output_path)

        return outputs

    def _export_reconstructed_psd(self, document: DocumentBackend, job: ExportJob, output_directory: Path) -> list[Path]:
        """기존 호출 호환을 위해 단일 PSD 레스터 변환 경로로 위임합니다."""

        # PSD 원본도 Photoshop 객체를 보존하지 않고 렌더링된 픽셀 레이어 PSD로 저장합니다.
        return self._export_reconstructed_document_psd(document, job, output_directory)

    def _export_reconstructed_document_psd(
        self, document: DocumentBackend, job: ExportJob, output_directory: Path
    ) -> list[Path]:
        """문서 백엔드의 선택 레이어를 하나의 새 레스터 PSD로 저장합니다."""

        output_path = resolve_output_path(
            output_directory,
            self._reconstructed_base_name(document, job),
            "psd",
            job.overwrite_existing,
            set(),
        )
        self.progress(f"PSD 재구성 변환 중: {output_path.name}")
        write_layers_to_psd(
            document,
            job.selected_layer_ids,
            output_path,
            preserve_canvas=True,
            rescale=job.rescale,
            layer_names=job.layer_names,
        )
        return [output_path]

    def _export_document_aseprite(self, document: DocumentBackend, job: ExportJob, output_directory: Path) -> list[Path]:
        """PSD 같은 비 Aseprite 문서 백엔드를 1프레임 Aseprite 파일들로 변환해 저장합니다."""

        outputs: list[Path] = []
        reserved_paths: set[Path] = set()

        for layer_id in job.selected_layer_ids:
            layer = self._job_layer(document, job, layer_id)
            base_name = build_base_name(job, layer)
            output_path = resolve_output_path(
                output_directory,
                base_name,
                "aseprite",
                job.overwrite_existing,
                reserved_paths,
            )
            self.progress(f"ASE 변환 중: {layer.display_name}")
            write_layers_to_aseprite(
                document,
                (layer_id,),
                output_path,
                preserve_canvas=job.preserve_canvas,
                rescale=job.rescale,
                layer_names=job.layer_names,
            )
            outputs.append(output_path)

        return outputs

    def _export_reconstructed_document_aseprite(
        self, document: DocumentBackend, job: ExportJob, output_directory: Path
    ) -> list[Path]:
        """PSD 같은 비 Aseprite 문서 백엔드를 선택 레이어만 가진 단일 Aseprite 파일로 저장합니다."""

        output_path = resolve_output_path(
            output_directory,
            self._reconstructed_base_name(document, job),
            "aseprite",
            job.overwrite_existing,
            set(),
        )
        self.progress(f"ASE 재구성 변환 중: {output_path.name}")
        write_layers_to_aseprite(
            document,
            job.selected_layer_ids,
            output_path,
            preserve_canvas=True,
            rescale=job.rescale,
            layer_names=job.layer_names,
        )
        return [output_path]

    def _export_aseprite(self, document: DocumentBackend, job: ExportJob, output_directory: Path) -> list[Path]:
        """선택 레이어 상태를 반영한 Aseprite 문서를 .aseprite 파일로 저장합니다."""

        from .ase_backend import AsepriteDocument

        if not isinstance(document, AsepriteDocument):
            raise PsdBackendError("ASE 내보내기는 Aseprite 원본 파일에서만 사용할 수 있습니다.")

        layer_ids = set(job.selected_layer_ids)
        selected_indices = {int(layer_id) for layer_id in layer_ids}
        first_layer = self._job_layer(document, job, job.selected_layer_ids[0])
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

    def _reconstructed_base_name(self, document: DocumentBackend, job: ExportJob) -> str:
        """원본 문서 스택에서 선택된 최상위 레이어 이름과 선택 개수로 파일명을 만듭니다."""

        # 레이어 선택 순서가 아니라 문서의 스택 순서를 뒤에서부터 확인해 실제 최상위 선택 레이어를 대표로 사용합니다.
        selected_layer_ids = job.selected_layer_ids
        selected = set(selected_layer_ids)
        representative_layer = next((layer for layer in reversed(document.layers) if layer.id in selected), None)
        if representative_layer is None:
            representative_layer = document.get_layer_info(selected_layer_ids[0])
        representative_layer = self._apply_job_layer_name(job, representative_layer)
        top_layer_name = representative_layer.path[0] if representative_layer.path else representative_layer.name
        return build_reconstructed_base_name(job, top_layer_name, len(selected_layer_ids))

    def _job_layer(self, document: DocumentBackend, job: ExportJob, layer_id: str) -> LayerInfo:
        """GUI에서 편집한 레이어명을 반영한 출력용 LayerInfo를 반환합니다."""

        layer = document.get_layer_info(layer_id)
        return self._apply_job_layer_name(job, layer)

    @staticmethod
    def _apply_job_layer_name(job: ExportJob, layer: LayerInfo) -> LayerInfo:
        """ExportJob의 레이어명 override를 LayerInfo 값 객체에 적용합니다."""

        new_name = (job.layer_names or {}).get(layer.id, "").strip()
        return replace(layer, name=new_name) if new_name else layer

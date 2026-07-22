from __future__ import annotations

from pathlib import Path

from PIL import Image

from .aseprite_codec import decode_aseprite_file, encode_aseprite_file, rename_layer, set_layer_visibility
from .aseprite_codec.constants import CEL_LINKED, COLOR_DEPTH_RGBA
from .aseprite_codec.errors import AseEditError, AseFormatError
from .aseprite_codec.model import CelChunk
from .blend_modes import LayerBlendMode, blend_mode_from_aseprite, composite_layer, normal_equivalent_layer
from .document_backend import ASEPRITE_EXTENSIONS, DocumentBackendError, DocumentFormat
from .models import LayerInfo


class AsepriteDocument:
    """Aseprite 파일을 공통 문서 백엔드 인터페이스로 노출합니다."""

    format = DocumentFormat.ASEPRITE

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._validate_input_path(self.path)
        self.ase_file = decode_aseprite_file(self.path)
        self._refresh_document_views()

    def _refresh_document_views(self) -> None:
        """Aseprite 모델 로드나 편집 뒤 GUI/Exporter용 캐시를 다시 구성합니다."""

        # 헤더와 프레임 목록에서 문서 단위 메타데이터를 동기화합니다.
        self.width = self.ase_file.header.width
        self.height = self.ase_file.header.height
        self.frame_count = len(self.ase_file.frames)
        self.layers = tuple(self._collect_layers())
        self._layers_by_id = {layer.id: layer for layer in self.layers}
        self._ase_layers_by_index = {layer.index: layer for layer in self.ase_file.layers}

    @staticmethod
    def _validate_input_path(path: Path) -> None:
        if not path.exists():
            raise DocumentBackendError(f"파일이 존재하지 않습니다: {path}")
        if path.suffix.lower() not in ASEPRITE_EXTENSIONS:
            supported = ", ".join(sorted(ASEPRITE_EXTENSIONS))
            raise DocumentBackendError(f"지원하지 않는 Aseprite 확장자입니다. 지원 형식: {supported}")

    @staticmethod
    def _validate_output_path(path: Path) -> None:
        if path.suffix.lower() not in ASEPRITE_EXTENSIONS:
            supported = ", ".join(sorted(ASEPRITE_EXTENSIONS))
            raise DocumentBackendError(f"Unsupported Aseprite output extension. Supported formats: {supported}")

    def save(self, path: Path | None = None) -> Path:
        """Encode the current Aseprite model and save it to disk."""

        target_path = self.path if path is None else Path(path)
        self._validate_output_path(target_path)
        try:
            encode_aseprite_file(self.ase_file, target_path)
        except (AseFormatError, OSError) as exc:
            raise DocumentBackendError(f"Could not save Aseprite file: {target_path}") from exc
        self.path = target_path
        return target_path

    def save_as(self, path: Path) -> Path:
        """Save the current Aseprite model to a new path and make it the active path."""

        return self.save(path)

    def rename_layer(self, layer_id: str, new_name: str) -> LayerInfo:
        """Rename a layer through the document backend and refresh cached layer views."""

        try:
            layer_index = self._layer_index_from_id(layer_id)
            self.ase_file = rename_layer(self.ase_file, layer_index, new_name)
        except (AseEditError, ValueError) as exc:
            raise DocumentBackendError(str(exc)) from exc
        self._refresh_document_views()
        return self.get_layer_info(layer_id)

    def set_layer_visibility(self, layer_id: str, visible: bool) -> LayerInfo:
        """Update a layer visibility flag through the document backend."""

        try:
            layer_index = self._layer_index_from_id(layer_id)
            self.ase_file = set_layer_visibility(self.ase_file, layer_index, visible)
        except (AseEditError, ValueError) as exc:
            raise DocumentBackendError(str(exc)) from exc
        self._refresh_document_views()
        return self.get_layer_info(layer_id)

    def _layer_index_from_id(self, layer_id: str) -> int:
        self.get_layer_info(layer_id)
        return int(layer_id)

    def _collect_layers(self) -> tuple[LayerInfo, ...]:
        parents_by_level: dict[int, str] = {}
        layer_infos: list[LayerInfo] = []
        for layer in self.ase_file.layers:
            path = tuple(parents_by_level[index] for index in range(layer.child_level) if index in parents_by_level)
            cel = self._find_renderable_cel(layer.index, frame_index=0)
            width = int(cel.width or 0) if cel is not None else 0
            height = int(cel.height or 0) if cel is not None else 0
            left = int(cel.x) if cel is not None else 0
            top = int(cel.y) if cel is not None else 0
            layer_infos.append(
                LayerInfo(
                    id=str(layer.index),
                    name=layer.name,
                    path=path,
                    visible=layer.visible,
                    width=width,
                    height=height,
                    left=left,
                    top=top,
                    blend_mode=blend_mode_from_aseprite(layer.blend_mode),
                )
            )
            parents_by_level[layer.child_level] = layer.name
            for level in list(parents_by_level):
                if level > layer.child_level:
                    del parents_by_level[level]
        return tuple(layer_infos)

    def get_layer_info(self, layer_id: str) -> LayerInfo:
        try:
            return self._layers_by_id[layer_id]
        except KeyError as exc:
            raise DocumentBackendError(f"레이어 ID를 찾을 수 없습니다: {layer_id}") from exc

    def render_layer(self, layer_id: str) -> Image.Image:
        layer_index = int(layer_id)
        cel = self._find_renderable_cel(layer_index, frame_index=0)
        if cel is None:
            return Image.new("RGBA", (1, 1), (0, 0, 0, 0))
        return self._cel_to_image(cel, self._layer_opacity(layer_index))

    def render_layer_for_png(self, layer_id: str) -> Image.Image:
        """Aseprite 특수 모드 레이어를 같은 하위 배경에서 사용할 Normal 등가 PNG 이미지로 렌더링합니다."""

        layer_info = self.get_layer_info(layer_id)
        source = self.render_layer(layer_id).convert("RGBA")
        if layer_info.blend_mode is LayerBlendMode.NORMAL:
            return source

        # Aseprite 레이어 인덱스는 아래에서 위 순서이므로 현재 인덱스보다 작은 표시 레이어를 합성합니다.
        target_index = int(layer_id)
        below_layer_ids = tuple(
            layer.id
            for layer in self.layers
            if int(layer.id) < target_index and layer.visible
        )
        backdrop = (
            self.render_composite(below_layer_ids)
            if below_layer_ids
            else Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        )
        return normal_equivalent_layer(
            backdrop,
            source,
            (layer_info.left, layer_info.top),
            layer_info.blend_mode,
        )

    def render_preview(self) -> Image.Image:
        """첫 프레임의 표시 레이어를 원본 블렌드 모드로 합성합니다."""

        # 일반 미리보기는 원본에서 표시 중인 레이어만 선택 합성 경로에 전달합니다.
        visible_layer_ids = tuple(str(layer.index) for layer in self.ase_file.layers if layer.visible)
        return self._render_frame_composite(visible_layer_ids, (self.width, self.height), 1.0)

    def render_composite(self, selected_layer_ids: tuple[str, ...]) -> Image.Image:
        """선택된 Aseprite 레이어를 첫 프레임 기준 블렌드 모드와 순서대로 합성합니다."""

        return self._render_frame_composite(selected_layer_ids, (self.width, self.height), 1.0)

    def render_preview_thumbnail(self, max_size: tuple[int, int]) -> Image.Image:
        """드롭 존 표시용 Aseprite 미리보기를 처음부터 축소 크기로 합성합니다."""

        # 원본 크기가 이미 표시 영역보다 작으면 기존 전체 미리보기와 같은 이미지를 반환합니다.
        target_size, scale = self._thumbnail_canvas_size(max_size)
        if scale >= 1:
            return self.render_preview()

        # 첫 프레임의 표시 레이어를 처음부터 축소한 캔버스에서 블렌드 합성합니다.
        visible_layer_ids = tuple(str(layer.index) for layer in self.ase_file.layers if layer.visible)
        return self._render_frame_composite(visible_layer_ids, target_size, scale)

    def render_layer_thumbnail(self, layer_id: str, max_size: tuple[int, int] = (48, 48)) -> Image.Image:
        image = self.render_layer(layer_id).convert("RGBA")
        image.thumbnail(max_size)
        return image

    def _thumbnail_canvas_size(self, max_size: tuple[int, int]) -> tuple[tuple[int, int], float]:
        """원본 캔버스와 요청 크기로 썸네일 캔버스 크기와 축소 배율을 계산합니다."""

        # thumbnail 동작처럼 원본보다 크게 확대하지 않고, 0 이하 요청값은 최소 1px로 보정합니다.
        max_width = max(1, int(max_size[0]))
        max_height = max(1, int(max_size[1]))
        source_width = max(1, int(self.width))
        source_height = max(1, int(self.height))
        scale = min(1.0, max_width / source_width, max_height / source_height)
        target_width = max(1, round(source_width * scale))
        target_height = max(1, round(source_height * scale))
        return (target_width, target_height), scale

    def _resize_for_preview_thumbnail(self, image: Image.Image, scale: float) -> Image.Image:
        """cel 이미지를 미리보기 배율에 맞게 축소합니다."""

        # 매우 얇은 cel도 썸네일에서 완전히 사라지지 않도록 각 축을 최소 1px로 유지합니다.
        width = max(1, round(image.width * scale))
        height = max(1, round(image.height * scale))
        return image.resize((width, height), Image.Resampling.LANCZOS)

    def _render_frame_composite(
        self,
        selected_layer_ids: tuple[str, ...],
        canvas_size: tuple[int, int],
        scale: float,
    ) -> Image.Image:
        """첫 프레임의 선택 레이어를 요청 캔버스 크기와 배율로 블렌드 합성합니다."""

        canvas = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
        if not self.ase_file.frames:
            return canvas

        # GUI 선택 여부가 원본 visibility와 다를 수 있으므로 전달받은 id 집합만 합성 조건으로 사용합니다.
        selected_indices = {int(layer_id) for layer_id in selected_layer_ids}
        frame = self.ase_file.frames[0]
        for cel in sorted(frame.cels, key=lambda item: (item.layer_index, item.z_index)):
            if cel.layer_index not in selected_indices:
                continue
            layer = self._ase_layers_by_index.get(cel.layer_index)
            if layer is None:
                continue
            renderable_cel = self._resolve_linked_cel(cel, frame_index=0)
            if renderable_cel is None:
                continue
            image = self._cel_to_image(renderable_cel, layer.opacity)
            if scale != 1:
                image = self._resize_for_preview_thumbnail(image, scale)
            canvas = composite_layer(
                canvas,
                image,
                (round(renderable_cel.x * scale), round(renderable_cel.y * scale)),
                blend_mode_from_aseprite(layer.blend_mode),
            )
        return canvas

    def _find_renderable_cel(self, layer_index: int, frame_index: int) -> CelChunk | None:
        if not self.ase_file.frames:
            return None
        frame = self.ase_file.frames[min(frame_index, len(self.ase_file.frames) - 1)]
        for cel in frame.cels:
            if cel.layer_index == layer_index:
                return self._resolve_linked_cel(cel, frame_index)
        return None

    def _resolve_linked_cel(self, cel: CelChunk, frame_index: int, visited: set[tuple[int, int]] | None = None) -> CelChunk | None:
        if cel.cel_type != CEL_LINKED:
            return cel
        if cel.linked_frame is None or cel.linked_frame >= len(self.ase_file.frames):
            raise DocumentBackendError(f"잘못된 linked cel frame입니다: {cel.linked_frame}")

        visited = visited or set()
        key = (frame_index, cel.layer_index)
        if key in visited:
            raise DocumentBackendError("linked cel 참조가 순환합니다.")
        visited.add(key)

        linked_frame = self.ase_file.frames[cel.linked_frame]
        for linked_cel in linked_frame.cels:
            if linked_cel.layer_index == cel.layer_index:
                return self._resolve_linked_cel(linked_cel, cel.linked_frame, visited)
        return None

    def _cel_to_image(self, cel: CelChunk, layer_opacity: int) -> Image.Image:
        if self.ase_file.header.color_depth != COLOR_DEPTH_RGBA:
            raise DocumentBackendError("현재 Aseprite 렌더링은 32bpp RGBA만 지원합니다.")
        if cel.width is None or cel.height is None or cel.pixels is None:
            raise DocumentBackendError("렌더링할 pixel payload가 없는 Cel입니다.")

        image = Image.frombytes("RGBA", (cel.width, cel.height), cel.pixels)
        opacity = max(0, min(255, round(cel.opacity * layer_opacity / 255)))
        if opacity < 255:
            r, g, b, a = image.split()
            a = a.point(lambda value: value * opacity // 255)
            image = Image.merge("RGBA", (r, g, b, a))
        return image

    def _layer_opacity(self, layer_index: int) -> int:
        layer = self._ase_layers_by_index.get(layer_index)
        return layer.opacity if layer is not None else 255

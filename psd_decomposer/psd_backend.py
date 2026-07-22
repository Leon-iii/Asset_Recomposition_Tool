from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from PIL import Image

from .blend_modes import LayerBlendMode, blend_mode_from_psd, normal_equivalent_layer
from .document_backend import DocumentBackendError, DocumentFormat
from .models import LayerInfo


PSD_EXTENSIONS = {".psd"}


class PsdBackendError(DocumentBackendError):
    """GUI에 그대로 표시할 수 있는 PSD 처리 오류입니다."""

    pass


def validate_input_path(path: Path) -> None:
    """입력 파일 존재 여부와 지원 확장자를 먼저 검증합니다."""

    if not path.exists():
        raise PsdBackendError(f"파일이 존재하지 않습니다: {path}")
    if path.suffix.lower() not in PSD_EXTENSIONS:
        supported = ", ".join(sorted(PSD_EXTENSIONS))
        raise PsdBackendError(f"지원하지 않는 확장자입니다. 지원 형식: {supported}")


class PsdDocument:
    """psd-tools로 PSD를 열고 레이어 탐색과 렌더링을 제공하는 어댑터입니다."""

    format = DocumentFormat.PSD

    def __init__(self, path: Path) -> None:
        validate_input_path(path)
        try:
            from psd_tools import PSDImage
        except ImportError as exc:
            raise PsdBackendError(
                "PSD 파일을 읽으려면 psd-tools가 필요합니다. requirements.txt를 먼저 설치하세요."
            ) from exc

        self.path = path
        self._psd = PSDImage.open(path)
        self.width, self.height = self._get_canvas_size()
        # PSD 입력은 정적 문서로 다루므로 드롭 존에는 1프레임으로 표시합니다.
        self.frame_count = 1
        self.layers = tuple(self._collect_layers())
        self._layers_by_id = {layer.id: layer for layer in self.layers}

    def _get_canvas_size(self) -> tuple[int, int]:
        """psd-tools 버전별 캔버스 크기 속성 차이를 흡수합니다."""

        size = getattr(self._psd, "size", None)
        if size:
            return int(size[0]), int(size[1])
        return int(getattr(self._psd, "width", 0)), int(getattr(self._psd, "height", 0))

    def _collect_layers(self) -> Iterable[LayerInfo]:
        """그룹 구조를 깊이 우선으로 순회해 내보낼 수 있는 아트 레이어만 수집합니다."""

        counter = 0

        def walk(nodes: Iterable[Any], group_path: tuple[str, ...]) -> Iterable[LayerInfo]:
            nonlocal counter
            for node in nodes:
                name = str(getattr(node, "name", "") or f"레이어 {counter + 1}")
                if getattr(node, "is_group", lambda: False)():
                    # 그룹은 출력 대상이 아니므로 경로에만 누적하고 내부 레이어를 계속 탐색합니다.
                    yield from walk(node, (*group_path, name))
                    continue

                left, top, right, bottom = getattr(node, "bbox", (0, 0, 0, 0))
                layer_id = str(counter)
                counter += 1
                yield LayerInfo(
                    id=layer_id,
                    name=name,
                    path=group_path,
                    visible=bool(getattr(node, "visible", True)),
                    width=max(0, int(right) - int(left)),
                    height=max(0, int(bottom) - int(top)),
                    left=int(left),
                    top=int(top),
                    blend_mode=blend_mode_from_psd(getattr(node, "blend_mode", b"norm")),
                )

        return walk(self._psd, ())

    def get_layer_node(self, layer_id: str) -> Any:
        """LayerInfo의 순번 기반 id에 대응하는 실제 psd-tools 레이어 객체를 찾습니다."""

        target_index = int(layer_id)
        index = 0

        def walk(nodes: Iterable[Any]) -> Any | None:
            nonlocal index
            for node in nodes:
                if getattr(node, "is_group", lambda: False)():
                    found = walk(node)
                    if found is not None:
                        return found
                    continue
                if index == target_index:
                    return node
                index += 1
            return None

        node = walk(self._psd)
        if node is None:
            raise PsdBackendError(f"레이어 ID를 찾을 수 없습니다: {layer_id}")
        return node

    def get_layer_info(self, layer_id: str) -> LayerInfo:
        """id로 캐시된 레이어 메타데이터를 조회합니다."""

        try:
            return self._layers_by_id[layer_id]
        except KeyError as exc:
            raise PsdBackendError(f"레이어 ID를 찾을 수 없습니다: {layer_id}") from exc

    def render_layer(self, layer_id: str):
        """단일 레이어를 투명 배경 이미지로 렌더링합니다."""

        node = self.get_layer_node(layer_id)
        image = node.composite()
        if image is None:
            raise PsdBackendError(f"레이어를 렌더링할 수 없습니다: {self.get_layer_info(layer_id).display_name}")
        return image

    def render_layer_for_png(self, layer_id: str) -> Image.Image:
        """PSD 특수 모드 레이어를 같은 하위 배경에서 사용할 Normal 등가 PNG 이미지로 렌더링합니다."""

        layer = self.get_layer_info(layer_id)
        source = self.render_layer(layer_id).convert("RGBA")
        if layer.blend_mode is LayerBlendMode.NORMAL:
            return source

        # psd-tools의 PSD 레이어 열거 순서는 아래에서 위이므로 현재 항목 앞의 표시 레이어가 하위 배경입니다.
        target_index = next(index for index, item in enumerate(self.layers) if item.id == layer_id)
        below_layer_ids = tuple(
            item.id
            for item in self.layers[:target_index]
            if self._is_layer_effectively_visible(item.id)
        )
        backdrop = (
            self.render_composite(below_layer_ids)
            if below_layer_ids
            else Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        )
        return normal_equivalent_layer(backdrop, source, (layer.left, layer.top), layer.blend_mode)

    def _is_layer_effectively_visible(self, layer_id: str) -> bool:
        """레이어 자체와 상위 PSD 그룹을 포함한 최종 표시 여부를 반환합니다."""

        node = self.get_layer_node(layer_id)
        is_visible = getattr(node, "is_visible", None)
        return bool(is_visible()) if callable(is_visible) else self.get_layer_info(layer_id).visible

    def render_composite(self, selected_layer_ids: tuple[str, ...]):
        """선택된 PSD 레이어만 원본 블렌드 모드와 스택 순서대로 합성합니다."""

        # 선택 레이어의 상위 그룹도 필터에 포함해 psd-tools가 중첩 레이어까지 순회할 수 있게 합니다.
        included_node_ids: set[int] = set()
        for layer_id in selected_layer_ids:
            node = self.get_layer_node(layer_id)
            while node is not None and node is not self._psd:
                included_node_ids.add(id(node))
                node = getattr(node, "parent", None)

        # 내장 미리보기를 우회하고 선택 필터를 강제해 현재 선택 상태를 정확히 렌더링합니다.
        image = self._psd.composite(
            ignore_preview=True,
            color=0.0,
            alpha=0.0,
            layer_filter=lambda node: id(node) in included_node_ids,
        )
        if image is None:
            raise PsdBackendError("선택된 PSD 레이어를 합성할 수 없습니다.")
        return image.convert("RGBA")

    def render_preview(self):
        """드롭 존에 표시할 PSD 전체 미리보기 이미지를 렌더링합니다."""

        # PSD 내부 preview 이미지는 투명 영역이 배경색으로 합성되어 있을 수 있으므로 투명 캔버스에 다시 합성합니다.
        image = self._psd.composite(ignore_preview=True, color=0.0, alpha=0.0)
        if image is None:
            raise PsdBackendError("PSD 미리보기 이미지를 생성할 수 없습니다.")
        return image.convert("RGBA")

    def render_preview_thumbnail(self, max_size: tuple[int, int]):
        """PSD 미리보기 썸네일은 기존 전체 합성 경로를 유지한 뒤 축소합니다."""

        # PSD 합성 의미를 바꾸지 않도록 render_preview 결과를 그대로 사용하고 표시 크기만 줄입니다.
        image = self.render_preview()
        image.thumbnail(max_size)
        return image

    def render_layer_thumbnail(self, layer_id: str, max_size: tuple[int, int] = (48, 48)):
        """레이어 선택 테이블에 사용할 작은 썸네일을 생성합니다."""

        node = self.get_layer_node(layer_id)
        image = self._render_layer_thumbnail_source(node)
        if image is None:
            # 빠른 픽셀 추출이 불가능한 복잡한 레이어는 기존 합성 경로로 되돌립니다.
            image = node.composite()
        if image is None:
            raise PsdBackendError(f"레이어를 렌더링할 수 없습니다: {self.get_layer_info(layer_id).display_name}")
        image = image.convert("RGBA")
        image.thumbnail(max_size)
        return image

    def _render_layer_thumbnail_source(self, node: Any):
        """PSD 레이어 썸네일용 원본 이미지를 빠른 픽셀 경로로 가져옵니다."""

        # 저장된 픽셀 채널이 있는 일반 레이어는 composite보다 가벼운 topil 경로를 먼저 사용합니다.
        if not getattr(node, "has_pixels", lambda: False)():
            return None
        topil = getattr(node, "topil", None)
        if topil is None:
            return None
        try:
            return topil(apply_icc=False)
        except Exception:
            # 일부 PSD 기능이나 손상된 채널에서 topil이 실패하면 정확한 composite 경로로 fallback합니다.
            return None

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

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

    def render_preview(self):
        """드롭 존에 표시할 PSD 전체 미리보기 이미지를 렌더링합니다."""

        # PSD 내부 preview 이미지는 투명 영역이 배경색으로 합성되어 있을 수 있으므로 투명 캔버스에 다시 합성합니다.
        image = self._psd.composite(ignore_preview=True, color=0.0, alpha=0.0)
        if image is None:
            raise PsdBackendError("PSD 미리보기 이미지를 생성할 수 없습니다.")
        return image.convert("RGBA")

    def render_layer_thumbnail(self, layer_id: str, max_size: tuple[int, int] = (48, 48)):
        """레이어 선택 테이블에 사용할 작은 썸네일을 생성합니다."""

        image = self.render_layer(layer_id).convert("RGBA")
        image.thumbnail(max_size)
        return image

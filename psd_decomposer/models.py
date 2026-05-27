from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


SUPPORTED_EXTENSIONS = {".psd"}


@dataclass(frozen=True)
class LayerInfo:
    """PSD 레이어 목록과 내보내기에서 공통으로 사용하는 레이어 메타데이터입니다."""

    id: str
    name: str
    path: tuple[str, ...]
    visible: bool
    width: int
    height: int
    left: int = 0
    top: int = 0

    @property
    def display_name(self) -> str:
        """그룹 경로를 포함한 사람이 읽기 쉬운 레이어 이름을 반환합니다."""

        return " / ".join((*self.path, self.name)) if self.path else self.name


@dataclass(frozen=True)
class ExportJob:
    """GUI에서 수집한 내보내기 옵션을 백그라운드 작업으로 전달하는 값 객체입니다."""

    source_path: Path
    output_directory: Path
    wrap_with_folder: bool
    include_original_name: bool
    include_layer_name: bool
    include_date: bool
    overwrite_existing: bool
    export_format: str
    rescale: int
    preserve_canvas: bool
    selected_layer_ids: tuple[str, ...]

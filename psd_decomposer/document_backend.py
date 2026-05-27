from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Protocol

from PIL import Image

from .models import LayerInfo


class DocumentFormat(Enum):
    """입력 문서의 원본 포맷을 구분합니다."""

    PSD = "psd"
    ASEPRITE = "aseprite"


SUPPORTED_EXTENSIONS = {".psd", ".ase", ".aseprite"}
ASEPRITE_EXTENSIONS = {".ase", ".aseprite"}


class DocumentBackendError(RuntimeError):
    """문서 로딩 계층에서 GUI에 전달할 수 있는 공통 오류입니다."""


class DocumentBackend(Protocol):
    """GUI와 Exporter가 파일 포맷과 무관하게 사용하는 문서 인터페이스입니다."""

    path: Path
    format: DocumentFormat
    width: int
    height: int
    layers: tuple[LayerInfo, ...]

    def get_layer_info(self, layer_id: str) -> LayerInfo: ...

    def render_layer(self, layer_id: str) -> Image.Image: ...

    def render_preview(self) -> Image.Image: ...

    def render_layer_thumbnail(self, layer_id: str, max_size: tuple[int, int] = (48, 48)) -> Image.Image: ...


def load_document(path: Path) -> DocumentBackend:
    """확장자에 맞는 문서 백엔드를 생성합니다."""

    suffix = path.suffix.lower()
    if suffix == ".psd":
        from .psd_backend import PsdDocument

        return PsdDocument(path)
    if suffix in ASEPRITE_EXTENSIONS:
        raise DocumentBackendError(".ase/.aseprite 파일은 입력 확장자만 준비되었고, 파서는 아직 구현되지 않았습니다.")

    supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
    raise DocumentBackendError(f"지원하지 않는 확장자입니다. 지원 형식: {supported}")


def is_supported_document(path: Path) -> bool:
    """파일 경로가 현재 입력으로 허용된 문서 확장자인지 확인합니다."""

    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def is_aseprite_document(path: Path) -> bool:
    """파일 경로가 Aseprite 문서 확장자인지 확인합니다."""

    return path.suffix.lower() in ASEPRITE_EXTENSIONS


def to_document_error(error: Exception) -> DocumentBackendError:
    """기존 PSD 오류 타입을 공통 문서 오류 타입으로 감싸서 호출부 처리를 단순화합니다."""

    from .psd_backend import PsdBackendError

    if isinstance(error, DocumentBackendError):
        return error
    if isinstance(error, PsdBackendError):
        return DocumentBackendError(str(error))
    return DocumentBackendError(str(error))

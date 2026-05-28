from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from .models import ExportJob, LayerInfo


INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_filename_part(value: str) -> str:
    """Windows 파일명에서 사용할 수 없는 문자를 안전한 문자로 치환합니다."""

    cleaned = INVALID_FILENAME_CHARS.sub("_", value).strip().strip(".")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned or "layer"


def build_output_directory(job: ExportJob) -> Path:
    """하위 폴더 묶기 옵션을 반영한 실제 출력 폴더를 계산합니다."""

    directory = job.output_directory
    if job.wrap_with_folder:
        directory = directory / f"{sanitize_filename_part(job.source_path.stem)}_decomposed"
    return directory


def build_base_name(job: ExportJob, layer: LayerInfo, today: date | None = None) -> str:
    """원본명, 레이어명, 날짜 옵션을 조합해 확장자 없는 기본 파일명을 만듭니다."""

    today = today or date.today()
    parts: list[str] = []
    if job.include_original_name:
        parts.append(job.source_path.stem)
    if job.include_layer_name:
        parts.append(layer.name)
    if job.include_date:
        parts.append(today.strftime("%y%m%d"))

    if not parts:
        parts.append(layer.name)
    return "_".join(sanitize_filename_part(part) for part in parts)


def build_reconstructed_base_name(
    job: ExportJob,
    top_layer_name: str,
    active_layer_count: int,
    today: date | None = None,
) -> str:
    """재구성 모드의 파일명 옵션을 최상위 레이어명과 활성 레이어 수 기준으로 조합합니다."""

    today = today or date.today()
    parts: list[str] = []
    if job.include_original_name:
        parts.append(job.source_path.stem)
    if job.include_layer_name:
        parts.append(top_layer_name)
    if job.include_layer_count:
        parts.append(f"{max(0, active_layer_count)}_Layers")
    if job.include_date:
        parts.append(today.strftime("%y%m%d"))

    if not parts:
        parts.append(top_layer_name)
    return "_".join(sanitize_filename_part(part) for part in parts)


def unique_output_path(directory: Path, base_name: str, extension: str) -> Path:
    """기존 파일과 충돌하지 않는 파일 경로를 순번 suffix로 찾습니다."""

    extension = extension.lower().lstrip(".")
    candidate = directory / f"{base_name}.{extension}"
    if not candidate.exists():
        return candidate

    index = 2
    while True:
        candidate = directory / f"{base_name}_{index}.{extension}"
        if not candidate.exists():
            return candidate
        index += 1


def resolve_output_path(
    directory: Path,
    base_name: str,
    extension: str,
    overwrite_existing: bool,
    reserved_paths: set[Path],
) -> Path:
    """덮어쓰기 옵션과 같은 배치 내 예약 경로를 모두 고려해 출력 경로를 정합니다."""

    extension = extension.lower().lstrip(".")
    candidate = directory / f"{base_name}.{extension}"
    # reserved_paths는 같은 내보내기 작업에서 방금 만든 파일을 자기 자신이 덮지 않게 막습니다.
    if candidate not in reserved_paths and (overwrite_existing or not candidate.exists()):
        reserved_paths.add(candidate)
        return candidate

    index = 2
    while True:
        candidate = directory / f"{base_name}_{index}.{extension}"
        if candidate not in reserved_paths and (overwrite_existing or not candidate.exists()):
            reserved_paths.add(candidate)
            return candidate
        index += 1

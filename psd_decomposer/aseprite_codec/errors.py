from __future__ import annotations


class AseFormatError(ValueError):
    """Aseprite 바이너리 구조가 명세와 맞지 않을 때 발생합니다."""


class AseUnsupportedFeatureError(AseFormatError):
    """파일은 Aseprite 형식이지만 현재 코덱이 아직 지원하지 않는 기능입니다."""


class AseEditError(AseFormatError):
    """Aseprite 중간 모델 편집 요청이 현재 문서 상태와 맞지 않을 때 발생합니다."""

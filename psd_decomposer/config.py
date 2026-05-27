from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


CONFIG_DIR  = Path.home() / ".psd_decomposition_tool"
CONFIG_PATH = CONFIG_DIR / "settings.json"


@dataclass
class AppSettings:
    """GUI에서 마지막으로 사용한 출력 옵션을 보관하는 사용자 설정입니다."""

    output_directory      : str = ""
    wrap_with_folder      : bool = True
    include_original_name : bool = True
    include_layer_name    : bool = True
    include_date          : bool = False
    overwrite_existing    : bool = False
    export_format         : str = "PNG"
    rescale               : int = 100
    preserve_canvas       : bool = True

    @classmethod
    def load(cls, path: Path = CONFIG_PATH) -> "AppSettings":
        """설정 파일을 읽고, 손상되었거나 범위를 벗어난 값은 기본값으로 복구합니다."""

        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()

        defaults = asdict(cls())
        # 이전 버전의 설정 파일에 없는 필드는 기본값을 유지하고, 알 수 없는 필드는 무시합니다.
        defaults.update({key: value for key, value in data.items() if key in defaults})
        settings = cls(**defaults)
        if settings.export_format not in {"PNG", "PSD"}:
            settings.export_format = "PNG"
        if settings.rescale not in {100, 200, 400, 800}:
            settings.rescale = 100
        return settings

    def save(self, path: Path = CONFIG_PATH) -> None:
        """현재 설정을 JSON 파일로 저장합니다."""

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

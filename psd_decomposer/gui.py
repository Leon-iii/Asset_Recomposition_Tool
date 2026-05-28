from __future__ import annotations

import queue
import threading
import tkinter as tk
import sys
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from .config import AppSettings
from .document_backend import DocumentBackend, DocumentBackendError, DocumentFormat, SUPPORTED_EXTENSIONS, load_document, to_document_error
from .exporter import Exporter
from .models import ExportJob, LayerInfo


DROP_ZONE_HEIGHT = 122
DROP_ZONE_PADDING = 10
LAYER_TABLE_RIGHT_PADDING = 8
OUTPUT_SETTINGS_WIDTH = 380
STATUS_PROGRESS_BAR_LENGTH = 380
STATUS_PROGRESS_BAR_THICKNESS = 15


@dataclass(frozen=True)
class ExportFormatState:
    """현재 문서/환경에 맞게 보정된 출력 형식 UI 상태입니다."""

    format_value: str
    psd_enabled: bool
    ase_enabled: bool
    warning_message: str


def resolve_export_format_state(
    document_format: DocumentFormat | None,
    psd_export_available: bool,
    psd_export_message: str,
    current_format: str,
) -> ExportFormatState:
    """문서 포맷과 Photoshop COM 상태를 기준으로 출력 형식 선택 가능 여부를 계산합니다."""

    if document_format is DocumentFormat.PSD:
        if psd_export_available:
            format_value = current_format if current_format in {"PNG", "PSD"} else "PNG"
            return ExportFormatState(format_value, True, False, psd_export_message)
        return ExportFormatState("PNG", False, False, psd_export_message)

    if document_format is DocumentFormat.ASEPRITE:
        format_value = current_format if current_format in {"PNG", "ASE"} else "PNG"
        return ExportFormatState(format_value, False, True, "PSD 내보내기는 PSD 원본 파일에서만 사용할 수 있습니다.")

    return ExportFormatState("PNG", False, False, "PSD 내보내기는 PSD 원본 파일을 먼저 로드한 뒤 사용할 수 있습니다.")


def build_drop_detail_text(width: int, height: int, frame_count: int) -> str:
    """드롭 존에 표시할 캔버스 크기와 전체 프레임 수 문구를 만듭니다."""

    return f"캔버스 크기: {width}x{height} px\n총 프레임 수: {frame_count}"


def resource_path(relative_path: str) -> Path:
    """개발 실행과 PyInstaller 빌드 실행 모두에서 리소스 파일을 찾습니다."""

    for base_path in resource_base_paths():
        candidate = base_path / relative_path
        if candidate.exists():
            return candidate
    return resource_base_paths()[0] / relative_path


def resource_base_paths() -> list[Path]:
    """아이콘 같은 번들 리소스를 찾기 위한 후보 루트 경로 목록을 반환합니다."""

    paths: list[Path] = []
    if hasattr(sys, "_MEIPASS"):
        paths.append(Path(sys._MEIPASS))
    if getattr(sys, "frozen", False):
        executable_dir = Path(sys.executable).resolve().parent
        paths.extend([executable_dir, executable_dir / "_internal"])
    paths.append(Path(__file__).resolve().parent.parent)
    return paths


try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError as exc:
    # 드래그 앤 드롭은 선택 기능이므로, 모듈이 없을 때도 파일 찾기 버튼으로 동작하게 둡니다.
    DND_FILES = None
    TkinterDnD = None
    TKINTERDND_IMPORT_ERROR = exc
else:
    TKINTERDND_IMPORT_ERROR = None


class PsdDecomposerApp:
    """지원 파일 입력, 레이어 선택, 출력 옵션, 내보내기 실행을 담당하는 Tkinter 앱입니다."""

    #region 초기화 및 윈도우 설정

    def __init__(self, root: tk.Tk) -> None:
        """애플리케이션 상태 변수를 준비하고 전체 GUI를 구성합니다."""

        # 기본 윈도우 설정
        self.root = root
        self.root.title("Asset Recomposition Tool v1.1")
        self._set_window_icon()
        self.root.minsize(820, 760)

        # 앱 상태 객체 초기화
        self.settings = AppSettings.load()
        self.document: DocumentBackend | None = None
        self.source_path: Path | None = None
        self.layer_vars: dict[str, tk.BooleanVar] = {}
        self.layer_name_vars: dict[str, tk.StringVar] = {}
        self.layer_photos: list[ImageTk.PhotoImage] = []
        self.preview_photo: ImageTk.PhotoImage | None = None
        self.select_all_check: ttk.Checkbutton | None = None
        self.is_updating_layer_selection = False
        self.worker_queue: queue.Queue[tuple[str, object]] = queue.Queue()

        # Tkinter 변수 초기화
        self.source_var = tk.StringVar()
        self.output_dir_var = tk.StringVar(value=self.settings.output_directory)
        self.wrap_var = tk.BooleanVar(value=self.settings.wrap_with_folder)
        self.name_original_var = tk.BooleanVar(value=self.settings.include_original_name)
        self.name_layer_var = tk.BooleanVar(value=self.settings.include_layer_name)
        self.name_layer_count_var = tk.BooleanVar(value=self.settings.include_layer_count)
        self.name_date_var = tk.BooleanVar(value=self.settings.include_date)
        self.overwrite_existing_var = tk.BooleanVar(value=self.settings.overwrite_existing)
        self.output_mode_var = tk.StringVar(value=self.settings.output_mode)
        self.psd_export_available, self.psd_export_message = self._detect_psd_export_status()
        self.psd_export_warning_message = self.psd_export_message
        if self.settings.export_format == "PSD" and not self.psd_export_available:
            self.settings.export_format = "PNG"
        self.format_var = tk.StringVar(value=self.settings.export_format)
        self.rescale_var = tk.IntVar(value=self.settings.rescale)
        self.layer_bounds_var = tk.StringVar(value="preserve" if self.settings.preserve_canvas else "crop")
        self.select_all_var = tk.BooleanVar(value=False)
        self.progress_var = tk.DoubleVar(value=0)
        self.status_var = tk.StringVar(value="PSD 또는 Aseprite 파일을 선택하거나 드래그 앤 드롭하세요.")

        # UI 생성 및 이벤트 연결
        self._build_ui()
        self._update_output_mode_controls()
        self._update_export_format_state()
        self._bind_drag_and_drop()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _set_window_icon(self) -> None:
        """실행 환경에 맞는 assets/app.ico를 찾아 Tkinter 창 아이콘으로 설정합니다."""

        # 개발 실행과 PyInstaller 빌드 실행 경로 모두에서 아이콘 탐색
        icon_path = resource_path("assets/app.ico")
        if icon_path.exists():
            self.root.iconbitmap(str(icon_path))

    #endregion

    #region UI 구성

    def _build_ui(self) -> None:
        """파일 입력, 경로, 레이어 테이블, 출력 설정, 상태 표시 영역을 배치합니다."""

        # 루트 레이아웃 및 공통 스타일 설정
        self.style = ttk.Style(self.root)
        self.style.configure("Status.Horizontal.TProgressbar", thickness=STATUS_PROGRESS_BAR_THICKNESS)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)

        # 파일 입력 영역 생성
        input_frame = ttk.LabelFrame(self.root, text="파일 입력", padding=12)
        input_frame.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))
        input_frame.columnconfigure(0, weight=1)

        # 드래그 앤 드롭 존 생성
        self.drop_zone = ttk.Frame(input_frame, padding=DROP_ZONE_PADDING, relief="ridge", height=DROP_ZONE_HEIGHT)
        self.drop_zone.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.drop_zone.grid_propagate(False)
        self.drop_zone.rowconfigure(0, weight=1)
        self.drop_zone.rowconfigure(1, weight=1)
        self.drop_zone.columnconfigure(1, weight=1)
        self.drop_image_label = ttk.Label(self.drop_zone, anchor="center")
        self.drop_title_label = ttk.Label(self.drop_zone, text="PSD 또는 Aseprite 파일을 여기에 드롭하세요", anchor="w")
        self.drop_detail_label = ttk.Label(self.drop_zone, text="또는 파일 찾기 버튼을 사용하세요.", anchor="w")
        self.drop_placeholder = ttk.Label(
            self.drop_zone,
            text="PSD 또는 Aseprite 파일을 여기에 드롭하세요.\n또는 파일 찾기 버튼을 사용하세요.",
            anchor="center",
            justify="center",
        )
        self.drop_placeholder.grid(row=0, column=0, rowspan=2, columnspan=2, sticky="nsew")

        # 파일 경로 영역은 입력 파일과 출력 폴더를 한곳에서 확인하고 수정할 수 있게 분리합니다.
        path_frame = ttk.LabelFrame(self.root, text="파일 경로", padding=12)
        path_frame.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))
        path_frame.columnconfigure(1, weight=1)

        # 입력 파일 경로 표시와 파일 찾기 버튼 배치
        ttk.Label(path_frame, text="입력 파일").grid(row=0, column=0, sticky="w")
        ttk.Entry(path_frame, textvariable=self.source_var, state="readonly").grid(row=0, column=1, sticky="ew", padx=(8, 0))
        ttk.Button(path_frame, text="파일 찾기...", command=self._browse_file).grid(row=0, column=2, padx=(8, 0))

        # 출력 폴더 경로 표시와 경로 찾기 버튼 배치
        output_dir_label = ttk.Label(path_frame, text="출력 폴더")
        output_dir_label.grid(row=1, column=0, sticky="w", pady=(8, 0))
        Tooltip(output_dir_label, "분리한 레이어 파일을 저장할 폴더입니다.\n파일이 로드되면 원본 파일이 있는 폴더로 갱신됩니다.")
        ttk.Entry(path_frame, textvariable=self.output_dir_var).grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(8, 0))
        ttk.Button(path_frame, text="경로 찾기...", command=self._browse_output_dir).grid(row=1, column=2, padx=(8, 0), pady=(8, 0))

        # 레이어 선택 영역과 출력 설정 영역을 담는 본문 레이아웃 생성
        body = ttk.Frame(self.root)
        body.grid(row=2, column=0, sticky="nsew", padx=12)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=0, minsize=OUTPUT_SETTINGS_WIDTH)
        body.rowconfigure(0, weight=1)

        # 레이어 선택 프레임 생성
        layer_frame = ttk.LabelFrame(body, text="레이어 선택", padding=12)
        layer_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        layer_frame.columnconfigure(0, weight=1)
        layer_frame.rowconfigure(1, weight=1)
        toolbar = ttk.Frame(layer_frame)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        # 스크롤 가능한 레이어 테이블 캔버스 구성
        canvas = tk.Canvas(layer_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(layer_frame, orient="vertical", command=canvas.yview)
        self.layer_list = ttk.Frame(canvas)
        self.layer_list.columnconfigure(3, weight=1)
        self.layer_list.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        self.layer_list_window = canvas.create_window((0, 0), window=self.layer_list, anchor="nw")
        canvas.bind(
            "<Configure>",
            lambda event: canvas.itemconfigure(
                self.layer_list_window,
                width=max(1, event.width - LAYER_TABLE_RIGHT_PADDING),
            ),
        )
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=1, column=0, sticky="nsew")
        scrollbar.grid(row=1, column=1, sticky="ns")

        # 오른쪽 패널은 고정 폭을 유지하고, 창 크기 변화는 왼쪽 레이어 영역만 받게 합니다.
        right_panel = ttk.Frame(body, width=OUTPUT_SETTINGS_WIDTH)
        right_panel.grid(row=0, column=1, sticky="ns", padx=(6, 0))
        right_panel.grid_propagate(False)
        right_panel.columnconfigure(0, weight=1)
        right_panel.rowconfigure(0, weight=1)

        # 출력 설정 영역 생성
        settings_frame = ttk.LabelFrame(right_panel, text="출력 설정", padding=12)
        settings_frame.grid(row=0, column=0, sticky="nsew")
        settings_frame.columnconfigure(1, weight=1)
        settings_frame.rowconfigure(11, weight=1)

        # 작동 모드는 출력 설정의 최상단에서 파일 생성 방식을 먼저 선택하게 합니다.
        output_mode_label = ttk.Label(settings_frame, text="작동 모드")
        output_mode_label.grid(row=0, column=0, sticky="w")
        mode_radio_frame = ttk.Frame(settings_frame)
        mode_radio_frame.grid(row=0, column=1, columnspan=2, sticky="w", padx=(8, 0))
        decompose_radio = ttk.Radiobutton(
            mode_radio_frame,
            text="분해",
            variable=self.output_mode_var,
            value="decompose",
            command=self._on_output_mode_changed,
        )
        decompose_radio.pack(side="left")
        Tooltip(decompose_radio, "선택한 레이어를 각각 별도 파일로 내보냅니다.")
        reconstruct_radio = ttk.Radiobutton(
            mode_radio_frame,
            text="재구성",
            variable=self.output_mode_var,
            value="reconstruct",
            command=self._on_output_mode_changed,
        )
        reconstruct_radio.pack(side="left", padx=(16, 0))
        Tooltip(reconstruct_radio, "선택한 레이어를 하나의 출력 파일로 합쳐 저장합니다.")
        ttk.Separator(settings_frame, orient="horizontal").grid(row=1, column=0, columnspan=3, sticky="ew", pady=(10, 14))

        # 폴더 묶기와 기존 출력물 삭제 옵션 배치
        file_options_frame = ttk.Frame(settings_frame)
        file_options_frame.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(0, 12))

        # 파일 옵션 서브프레임 내부는 pack으로 좌우 항목을 고정 간격 배치합니다.
        self.wrap_check = ttk.Checkbutton(file_options_frame, variable=self.wrap_var)
        self.wrap_check.pack(side="left")
        wrap_label = ttk.Label(file_options_frame, text="하위 폴더로 묶기")
        wrap_label.pack(side="left", padx=(6, 24))
        Tooltip(wrap_label, '내보낸 파일을 "(원본 파일명)_decomposed" 하위 폴더 안에 저장합니다.')

        ttk.Checkbutton(file_options_frame, variable=self.overwrite_existing_var).pack(side="left")
        overwrite_label = ttk.Label(file_options_frame, text="기존 출력물 삭제")
        overwrite_label.pack(side="left", padx=(6, 0))
        Tooltip(overwrite_label, "저장할 파일명과 같은 기존 파일이 있으면 덮어씁니다.\n같은 배치에서 새로 만든 파일끼리는 덮어쓰지 않습니다.")
        ttk.Separator(settings_frame, orient="horizontal").grid(row=3, column=0, columnspan=3, sticky="ew", pady=(0, 14))

        # 파일 이름 구성 옵션 배치
        file_name_label = ttk.Label(settings_frame, text="파일 이름")
        file_name_label.grid(row=4, column=0, sticky="w")
        Tooltip(file_name_label, "내보낼 파일명에 포함할 항목입니다.\n여러 항목을 선택하면 언더스코어로 이어 붙입니다.")

        # 파일명 옵션은 두 개의 서브프레임으로 분리하고 내부 항목은 pack으로 정렬합니다.
        name_top_frame = ttk.Frame(settings_frame)
        name_top_frame.grid(row=4, column=1, columnspan=2, sticky="w", padx=(8, 0))
        name_bottom_frame = ttk.Frame(settings_frame)
        name_bottom_frame.grid(row=5, column=1, columnspan=2, sticky="w", padx=(8, 0), pady=(4, 0))

        # 각 파일명 조합 옵션에는 실제 파일명에 붙는 조각 예시를 툴팁으로 안내합니다.
        name_original_check = ttk.Checkbutton(
            name_top_frame,
            text="원본 파일명",
            variable=self.name_original_var,
            width=12,
        )
        name_original_check.pack(side="left")
        Tooltip(name_original_check, "입력 파일의 이름을 출력 파일명에 포함합니다.\n예: character.psd -> character")

        name_layer_check = ttk.Checkbutton(
            name_top_frame,
            text="레이어명",
            variable=self.name_layer_var,
            width=12,
        )
        name_layer_check.pack(side="left")
        Tooltip(name_layer_check, "분해 모드에서는 각 레이어 이름을, 재구성 모드에서는 최상위 선택 레이어 이름을 포함합니다.\n예: Shadow")
        ttk.Label(settings_frame, text="").grid(row=5, column=0, sticky="w")
        self.layer_count_check = ttk.Checkbutton(
            name_bottom_frame,
            text="레이어 수",
            variable=self.name_layer_count_var,
            width=12,
        )
        self.layer_count_check.pack(side="left")
        Tooltip(self.layer_count_check, "재구성 모드에서 선택된 레이어 개수를 출력 파일명에 포함합니다.\n예: 3_Layers")

        name_date_check = ttk.Checkbutton(
            name_bottom_frame,
            text="날짜",
            variable=self.name_date_var,
            width=12,
        )
        name_date_check.pack(side="left")
        Tooltip(name_date_check, "오늘 날짜를 출력 파일명에 포함합니다.\n예: 20260529")

        # 출력 형식 라디오 버튼 배치
        export_format_label = ttk.Label(settings_frame, text="출력 형식")
        export_format_label.grid(row=6, column=0, sticky="w", pady=(14, 0))
        Tooltip(export_format_label, "PSD 또는 PNG로 저장합니다.\nPSD 저장은 Windows Photoshop 자동화가 필요합니다.")
        format_frame = ttk.Frame(settings_frame)
        format_frame.grid(row=6, column=1, columnspan=2, sticky="w", padx=(8, 0), pady=(14, 0))
        # 출력 형식 선택지는 pack 간격으로 한 줄에 정렬합니다.
        self.psd_radio = ttk.Radiobutton(format_frame, text="PSD", variable=self.format_var, value="PSD")
        self.psd_radio.pack(side="left")
        self.psd_radio.bind("<Button-1>", self._show_psd_unavailable_warning)
        if not self.psd_export_available:
            self.psd_radio.configure(state="disabled")
        ttk.Radiobutton(format_frame, text="PNG", variable=self.format_var, value="PNG").pack(side="left", padx=(16, 0))
        self.ase_radio = ttk.Radiobutton(format_frame, text="ASE", variable=self.format_var, value="ASE")
        self.ase_radio.pack(side="left", padx=(16, 0))

        # 확대 비율 라디오 버튼 배치
        rescale_label = ttk.Label(settings_frame, text="확대 비율")
        rescale_label.grid(row=7, column=0, sticky="w", pady=(14, 0))
        Tooltip(rescale_label, "저장할 이미지 크기 배율입니다.\n100%는 원본 크기 그대로 저장합니다.")
        rescale_frame = ttk.Frame(settings_frame)
        rescale_frame.grid(row=7, column=1, columnspan=2, sticky="w", padx=(8, 0), pady=(14, 0))
        # 확대 비율은 pack 간격으로 같은 행에 배치합니다.
        for index, value in enumerate((100, 200, 400, 800)):
            ttk.Radiobutton(rescale_frame, text=f"{value}%", variable=self.rescale_var, value=value).pack(
                side="left",
                padx=(0 if index == 0 else 16, 0),
            )

        # 레이어 영역 저장 방식 라디오 버튼 배치
        layer_bounds_label = ttk.Label(settings_frame, text="레이어 영역")
        layer_bounds_label.grid(row=8, column=0, sticky="w", pady=(14, 0))
        Tooltip(layer_bounds_label, "원본 캔버스 위치를 유지하거나,\n레이어 오브젝트 영역만 잘라 저장할지 선택합니다.")
        bounds_frame = ttk.Frame(settings_frame)
        bounds_frame.grid(row=8, column=1, columnspan=2, sticky="w", padx=(8, 0), pady=(14, 0))
        # 레이어 영역 옵션도 pack으로 위아래 순서를 고정합니다.
        self.preserve_bounds_radio = ttk.Radiobutton(
            bounds_frame,
            text="원본 캔버스와 위치 유지",
            variable=self.layer_bounds_var,
            value="preserve",
        )
        self.preserve_bounds_radio.pack(anchor="w")
        self.crop_bounds_radio = ttk.Radiobutton(
            bounds_frame,
            text="레이어 오브젝트만 크롭",
            variable=self.layer_bounds_var,
            value="crop",
        )
        self.crop_bounds_radio.pack(anchor="w", pady=(2, 0))

        # Aseprite 원본 편집 내용 저장 버튼은 Aseprite 문서가 로드된 경우에만 활성화합니다.
        ase_save_frame = ttk.Frame(settings_frame)
        ase_save_frame.grid(row=9, column=0, columnspan=3, sticky="ew", pady=(16, 0))
        ase_save_label = ttk.Label(ase_save_frame, text="Aseprite 저장")
        ase_save_label.pack(side="left")
        Tooltip(ase_save_label, "레이어 이름과 표시 상태 변경을 Aseprite 파일에 저장합니다.")
        self.save_ase_button = ttk.Button(
            ase_save_frame,
            text="저장",
            command=lambda: None,
            state="disabled",
        )
        self.save_ase_as_button = ttk.Button(
            ase_save_frame,
            text="다른 이름으로 저장...",
            command=lambda: None,
            state="disabled",
        )
        self.save_ase_as_button.pack(side="right", padx=(8, 0))
        self.save_ase_button.pack(side="right", padx=(8, 0))
        ase_save_frame.grid_remove()

        # 내보내기 버튼은 출력 설정 그룹의 최하단에 고정합니다.
        self.export_button = ttk.Button(
            settings_frame,
            text="선택한 레이어 내보내기",
            command=self._start_export,
            state="disabled",
        )
        self.export_button.grid(
            row=12, column=0, columnspan=3, sticky="ew", pady=(12, 0)
        )

        # 하단 상태 메시지와 진행 막대 생성
        status_frame = ttk.Frame(self.root)
        status_frame.grid(row=3, column=0, sticky="ew", padx=12, pady=12)
        status_frame.columnconfigure(0, weight=1)
        ttk.Label(status_frame, textvariable=self.status_var, anchor="w").grid(row=0, column=0, sticky="ew")
        self.progress_bar = ttk.Progressbar(
            status_frame,
            variable=self.progress_var,
            maximum=100,
            length=STATUS_PROGRESS_BAR_LENGTH,
            style="Status.Horizontal.TProgressbar",
        )

    #endregion

    #region 출력 모드 상태

    def _on_output_mode_changed(self) -> None:
        """작동 모드 변경 시 재구성 모드의 고정 옵션을 즉시 GUI에 반영합니다."""

        # 라디오 버튼에서 바뀐 모드에 맞춰 의존 옵션을 잠그거나 해제합니다.
        self._update_output_mode_controls()

    def _update_output_mode_controls(self) -> None:
        """재구성 모드에서 하위 폴더 묶기와 레이어 crop 옵션을 비활성화합니다."""

        # 재구성 모드는 단일 파일을 원본 캔버스 기준으로 만들기 때문에 관련 옵션을 강제로 보정합니다.
        is_reconstruct = self.output_mode_var.get() == "reconstruct"
        if is_reconstruct:
            self.wrap_var.set(False)
            self.layer_bounds_var.set("preserve")
        else:
            # 분해 모드는 레이어별 출력이므로 레이어 수 파일명 옵션을 사용하지 않습니다.
            self.name_layer_count_var.set(False)
        control_state = "disabled" if is_reconstruct else "normal"
        self.wrap_check.configure(state=control_state)
        self.preserve_bounds_radio.configure(state=control_state)
        self.crop_bounds_radio.configure(state=control_state)
        self.layer_count_check.configure(state="normal" if is_reconstruct else "disabled")

    #endregion

    #region 드래그 앤 드롭

    def _bind_drag_and_drop(self) -> None:
        """드롭 존과 내부 라벨에 동일한 파일 드롭 이벤트를 연결합니다."""

        # tkinterdnd2를 사용할 수 없는 경우 안내 문구로 대체
        if TkinterDnD is None or DND_FILES is None:
            message = "드래그 앤 드롭을 사용하려면 tkinterdnd2가 필요합니다."
            if TKINTERDND_IMPORT_ERROR is not None:
                message = f"{message}\n감지된 오류: {TKINTERDND_IMPORT_ERROR}"
            self.drop_detail_label.configure(text=message)
            self.drop_placeholder.configure(text=f"{message}\n파일 찾기 버튼을 사용하세요.")
            return

        # Windows의 tkinterdnd2는 마우스 아래의 실제 하위 위젯에 따라 Drop 이벤트가 달라질 수 있습니다.
        # 루트와 드롭 존 전체에 함께 등록해 placeholder/썸네일/라벨 위에서도 같은 핸들러가 호출되게 합니다.
        # 드롭 이벤트를 받을 위젯 전체 등록
        for widget in self._drop_target_widgets():
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self._handle_drop)

    def _drop_target_widgets(self) -> tuple[tk.Widget, ...]:
        """드롭 이벤트를 받아야 하는 루트와 드롭 존 하위 위젯을 반환합니다."""

        return (
            self.root,
            self.drop_zone,
            self.drop_image_label,
            self.drop_title_label,
            self.drop_detail_label,
            self.drop_placeholder,
        )

    #endregion

    #region PSD 내보내기 가용성

    def _detect_psd_export_status(self) -> tuple[bool, str]:
        """PSD 저장에 필요한 pywin32와 Photoshop COM 등록 상태를 확인합니다."""

        # pywin32 설치 여부 확인
        try:
            import win32com.client  # noqa: F401
        except ImportError:
            return False, "PSD 저장에는 pywin32와 설치된 Photoshop이 필요합니다."

        # Photoshop COM 등록 여부 확인
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"Photoshop.Application\CLSID"):
                return True, "PSD 저장 가능"
        except OSError:
            return False, "Photoshop COM 등록을 찾을 수 없습니다. Photoshop 설치 상태를 확인하세요."

    def _show_psd_unavailable_warning(self, _event=None) -> str:
        """비활성화된 PSD 라디오 버튼을 눌렀을 때 사유를 알려줍니다."""

        if self.psd_radio.instate(["!disabled"]):
            return ""

        messagebox.showwarning("PSD 저장 불가", self.psd_export_warning_message)
        return "break"

    #endregion

    #region 파일 선택 및 로드

    def _browse_file(self) -> None:
        """파일 선택 대화상자에서 지원 문서를 선택해 로드합니다."""

        # 지원 파일 형식 필터 구성
        filetypes = [
            ("지원 파일", "*.psd *.ase *.aseprite"),
            ("PSD 파일", "*.psd"),
            ("Aseprite 파일", "*.ase *.aseprite"),
            ("모든 파일", "*.*"),
        ]

        # 선택한 파일 로드
        selected = filedialog.askopenfilename(title="파일 열기", filetypes=filetypes)
        if selected:
            self._load_file(Path(selected))

    def _browse_output_dir(self) -> None:
        """출력 폴더 선택 대화상자를 열고 선택값을 반영합니다."""

        # 선택한 폴더를 출력 경로에 반영
        selected = filedialog.askdirectory(title="출력 폴더 선택")
        if selected:
            self.output_dir_var.set(selected)

    def _handle_drop(self, event) -> None:
        """드롭된 파일 목록 중 첫 번째 파일을 입력 문서로 처리합니다."""

        # 드롭된 경로 목록에서 첫 번째 파일만 사용
        paths = self.root.tk.splitlist(event.data)
        if paths:
            self._load_file(Path(paths[0]))

    def _load_file(self, path: Path) -> None:
        """지원 문서를 열고 미리보기, 출력 폴더, 레이어 테이블을 갱신합니다."""

        # 지원하지 않는 확장자는 기존 로드 상태를 유지하고 경고만 표시
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            # 잘못된 확장자는 기존에 로드된 파일 상태를 유지한 채 경고만 표시합니다.
            supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
            messagebox.showwarning("지원하지 않는 파일", f"지원 형식: {supported}")
            return

        # 실패 시 복구할 이전 표시 상태 저장
        previous_status = self.status_var.get()
        previous_placeholder_text = self.drop_placeholder.cget("text")
        had_loaded_file = self.source_path is not None

        # 파일 처리 중 상태 표시
        self._show_file_processing_message()
        try:
            document = load_document(path)
            preview_image = document.render_preview()
        except Exception as exc:
            # 로드 실패 시 드롭 존과 상태 문구 원상복구
            self._restore_drop_zone_after_failed_load(had_loaded_file, previous_placeholder_text, previous_status)
            messagebox.showerror("파일 열기 실패", str(to_document_error(exc)))
            return

        # 로드 성공 상태 반영
        self.document = document
        self.source_path = path
        self.source_var.set(str(path))
        # 새 파일을 열면 출력 폴더도 해당 원본 파일이 있는 폴더로 자동 동기화합니다.
        self.output_dir_var.set(str(path.parent))

        # 미리보기와 레이어 목록 갱신
        self._update_drop_zone(path, preview_image, self.document.frame_count)
        self._populate_layers(self.document.layers)
        self._update_export_format_state()

        # 진행 표시 초기화 및 완료 메시지 표시
        self.progress_var.set(0)
        self._hide_progress_bar()
        self.status_var.set(f"{path.name}에서 레이어 {len(self.document.layers)}개를 불러왔습니다.")

    def _restore_drop_zone_after_failed_load(
        self,
        had_loaded_file: bool,
        placeholder_text: str,
        status_text: str,
    ) -> None:
        """파일 로드 실패 시 드롭 존을 시도 직전 상태로 되돌립니다."""

        # 진행 상태 초기화
        self.progress_var.set(0)
        self._hide_progress_bar()
        self.status_var.set(status_text)
        # 기존 파일이 있던 경우 기존 썸네일/파일 정보 표시 복구
        if had_loaded_file:
            self.drop_placeholder.grid_remove()
            self.drop_image_label.grid(row=0, column=0, rowspan=2, sticky="nsw")
            self.drop_title_label.grid(row=0, column=1, sticky="sew", padx=(10, 0))
            self.drop_detail_label.grid(row=1, column=1, sticky="new", padx=(10, 0), pady=(4, 0))
            return

        # 기존 파일이 없던 경우 안내 문구 표시 복구
        self.drop_image_label.grid_remove()
        self.drop_title_label.grid_remove()
        self.drop_detail_label.grid_remove()
        self.drop_placeholder.configure(text=placeholder_text)
        self.drop_placeholder.grid(row=0, column=0, rowspan=2, columnspan=2, sticky="nsew")

    def _show_file_processing_message(self) -> None:
        """파일 로드가 시작되었음을 드롭 존과 하단 상태 영역에 즉시 표시합니다."""

        # 기존 드롭 존 내용을 숨기고 처리 중 안내 문구 표시
        self.drop_image_label.grid_remove()
        self.drop_title_label.grid_remove()
        self.drop_detail_label.grid_remove()
        self.drop_placeholder.configure(text="파일 처리 중...")
        self.drop_placeholder.grid(row=0, column=0, rowspan=2, columnspan=2, sticky="nsew")
        # 진행 막대와 상태 메시지 표시
        self.progress_var.set(0)
        self._show_progress_bar()
        self.status_var.set("파일 처리 중...")
        self.root.update_idletasks()

    def _update_drop_zone(self, path: Path, preview_image: Image.Image, frame_count: int) -> None:
        """드롭 존을 안내 문구에서 파일 썸네일과 파일 정보 표시로 전환합니다."""

        # 파일 정보 표시 레이아웃으로 전환
        self.drop_placeholder.grid_remove()
        self.drop_zone.rowconfigure(0, weight=1)
        self.drop_zone.rowconfigure(1, weight=1)
        self.drop_image_label.grid(row=0, column=0, rowspan=2, sticky="nsw")
        self.drop_title_label.grid(row=0, column=1, sticky="sew", padx=(10, 0))
        self.drop_detail_label.grid(row=1, column=1, sticky="new", padx=(10, 0), pady=(4, 0))
        # 원본 프리뷰 이미지로 드롭 존 썸네일 생성
        thumbnail = preview_image.convert("RGBA")
        thumbnail.thumbnail(self._drop_zone_thumbnail_size())
        self.preview_photo = ImageTk.PhotoImage(thumbnail)
        self.drop_image_label.configure(image=self.preview_photo)
        # 파일명, 캔버스 크기, 전체 프레임 수 표시
        self.drop_title_label.configure(text=f"{path.stem}{path.suffix}")
        self.drop_detail_label.configure(
            text=build_drop_detail_text(preview_image.width, preview_image.height, frame_count)
        )

    def _drop_zone_thumbnail_size(self) -> tuple[int, int]:
        """현재 드롭 존 높이에 맞춰 원본 파일 썸네일의 최대 크기를 계산합니다."""

        # 실제 렌더링된 드롭 존 높이 확인
        self.drop_zone.update_idletasks()
        height = self.drop_zone.winfo_height()
        if height <= 1:
            height = DROP_ZONE_HEIGHT
        # 드롭 존 안쪽 여백을 제외한 썸네일 최대 크기 계산
        max_height = max(48, height - DROP_ZONE_PADDING * 2)
        max_width = round(max_height * 1.5)
        return max_width, max_height

    #endregion

    #region 레이어 테이블 및 선택 상태

    def _create_layer_photo(self, layer_id: str) -> ImageTk.PhotoImage:
        """레이어 썸네일을 만들고, 실패 시 투명 이미지로 테이블 레이아웃을 유지합니다."""

        assert self.document is not None
        # 레이어 렌더링 실패 시 빈 썸네일로 대체
        try:
            thumbnail = self.document.render_layer_thumbnail(layer_id)
        except DocumentBackendError:
            thumbnail = Image.new("RGBA", (48, 48), (0, 0, 0, 0))
        return ImageTk.PhotoImage(thumbnail)

    def _set_all_layers(self, selected: bool) -> None:
        """전체 선택 체크박스에서 개별 레이어 체크 상태를 일괄 변경합니다."""

        # 역방향 상태 갱신이 중복 호출되지 않도록 플래그 설정
        self.is_updating_layer_selection = True
        for var in self.layer_vars.values():
            var.set(selected)
        self.is_updating_layer_selection = False
        # 전체 선택 표시와 내보내기 버튼 상태 재계산
        self._update_layer_selection_state()

    def _toggle_select_all(self) -> None:
        """전체 선택 체크박스의 true/false/alternate 상태를 개별 체크박스에 전파합니다."""

        # 내부 갱신 중 발생한 이벤트는 무시
        if self.is_updating_layer_selection:
            return
        # 중간 상태에서 클릭하면 전체 선택으로 전환
        if "alternate" in self.select_all_check.state():
            self._set_all_layers(True)
        elif self.select_all_var.get():
            self._set_all_layers(True)
        else:
            self._set_all_layers(False)

    def _on_layer_selection_changed(self) -> None:
        """개별 레이어 선택 변경을 전체 선택 상태와 내보내기 버튼 상태에 반영합니다."""

        # 전체 선택에서 내려온 갱신이 아닌 사용자 변경만 처리
        if not self.is_updating_layer_selection:
            self._update_layer_selection_state()

    def _update_layer_selection_state(self) -> None:
        """선택 개수를 기준으로 전체 선택의 alternate 상태와 버튼 활성화를 계산합니다."""

        # 현재 선택 개수 계산
        selected_count = sum(1 for var in self.layer_vars.values() if var.get())
        total_count = len(self.layer_vars)
        control_state = "normal" if total_count > 0 else "disabled"

        # 전체 선택 체크박스 상태 동기화
        self.is_updating_layer_selection = True
        if self.select_all_check is not None:
            self.select_all_check.configure(state=control_state)
            if total_count > 0 and 0 < selected_count < total_count:
                # 일부만 선택된 상태는 ttk의 alternate state로 표현합니다.
                self.select_all_var.set(False)
                self.select_all_check.state(["alternate"])
            else:
                self.select_all_check.state(["!alternate"])
                self.select_all_var.set(total_count > 0 and selected_count == total_count)
        self.is_updating_layer_selection = False

        # 선택된 레이어가 있을 때만 내보내기 버튼 활성화
        self.export_button.configure(state="normal" if selected_count > 0 else "disabled")

    def _current_selected_layer_ids(self) -> tuple[str, ...]:
        """현재 체크된 레이어 id만 내보내기 순서대로 반환합니다."""

        # 체크된 레이어 ID 수집
        return tuple(layer_id for layer_id, var in self.layer_vars.items() if var.get())

    def _populate_layers(self, layers: tuple[LayerInfo, ...]) -> None:
        """레이어 선택, 썸네일, 크기, Aseprite 이름 편집 테이블을 다시 구성합니다."""

        # 이전 파일에서 생성한 레이어 행과 선택 상태를 모두 초기화합니다.
        for child in self.layer_list.winfo_children():
            child.destroy()
        self.select_all_check = None
        self.layer_vars.clear()
        self.layer_name_vars.clear()
        self.layer_photos.clear()

        # 내보낼 수 있는 레이어가 없으면 빈 상태 메시지만 표시합니다.
        if not layers:
            ttk.Label(self.layer_list, text="내보낼 수 있는 레이어가 없습니다.").pack(anchor="w")
            self._update_layer_selection_state()
            return

        # 파일 내부 레이어 수집 방향과 반대로 보여 주어 사용자가 보는 순서를 맞춥니다.
        display_layers = tuple(reversed(layers))
        can_edit_aseprite = self._is_aseprite_document()

        # 첫 칸에는 전체 선택 체크박스를 두고, 나머지 칸은 레이어 속성 헤더를 표시합니다.
        self.select_all_check = ttk.Checkbutton(
            self.layer_list,
            variable=self.select_all_var,
            command=self._toggle_select_all,
            state="disabled",
        )
        self.select_all_check.grid(row=0, column=0, sticky="", padx=(0, 8), pady=(0, 6))
        ttk.Label(self.layer_list, text="미리보기", anchor="center").grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=(0, 6))
        ttk.Label(self.layer_list, text="크기", anchor="center").grid(row=0, column=2, sticky="ew", padx=(0, 8), pady=(0, 6))
        ttk.Label(self.layer_list, text="레이어 이름", anchor="w").grid(row=0, column=3, sticky="ew", pady=(0, 6))
        ttk.Separator(self.layer_list, orient="horizontal").grid(row=1, column=0, columnspan=4, sticky="ew", pady=(0, 4))

        # 각 레이어를 한 행으로 만들고 행 사이에 구분선을 배치합니다.
        for index, layer in enumerate(display_layers):
            row = 2 + index * 2
            selected_var = tk.BooleanVar(value=layer.visible)
            name_var = tk.StringVar(value=layer.name)
            self.layer_vars[layer.id] = selected_var
            self.layer_name_vars[layer.id] = name_var

            # 레이어 썸네일은 Tk 이미지 참조가 사라지지 않도록 리스트에 보관합니다.
            photo = self._create_layer_photo(layer.id)
            self.layer_photos.append(photo)
            self.layer_list.rowconfigure(row, minsize=56)

            # 선택, 썸네일, 크기, 이름 셀을 같은 행 높이 안에서 가운데 정렬합니다.
            ttk.Checkbutton(
                self.layer_list,
                variable=selected_var,
                command=self._on_layer_selection_changed,
            ).grid(row=row, column=0, sticky="", padx=(0, 8), pady=4)
            ttk.Label(self.layer_list, image=photo, anchor="center").grid(row=row, column=1, sticky="", padx=(0, 8), pady=4)
            ttk.Label(
                self.layer_list,
                text=f"{layer.width:02d}x{layer.height:02d}",
                anchor="center",
            ).grid(row=row, column=2, sticky="ew", padx=(0, 8), pady=4)
            if can_edit_aseprite:
                name_entry = ttk.Entry(self.layer_list, textvariable=name_var)
                name_entry.bind("<FocusOut>", lambda _event, layer_id=layer.id: self._on_layer_name_committed(layer_id))
                name_entry.bind("<Return>", lambda _event, layer_id=layer.id: self._on_layer_name_committed(layer_id))
                name_entry.grid(row=row, column=3, sticky="ew", pady=4)
            else:
                ttk.Label(self.layer_list, text=layer.display_name, anchor="w").grid(row=row, column=3, sticky="ew", pady=4)
            ttk.Separator(self.layer_list, orient="horizontal").grid(row=row + 1, column=0, columnspan=4, sticky="ew", pady=(0, 1))

        # 생성된 선택 상태를 기준으로 전체 선택 체크박스와 내보내기 버튼을 동기화합니다.
        self._update_layer_selection_state()

    def _is_aseprite_document(self) -> bool:
        """현재 로드된 문서가 Aseprite 문서인지 확인합니다."""

        return self.document is not None and self.document.format is DocumentFormat.ASEPRITE

    def _on_layer_name_committed(self, layer_id: str) -> str:
        """Aseprite 레이어 이름 입력칸의 변경 내용을 GUI 모델에 보정합니다."""

        if not self._is_aseprite_document() or self.document is None:
            return "break"
        name_var = self.layer_name_vars[layer_id]
        current_layer = self.document.get_layer_info(layer_id)
        new_name = name_var.get().strip()
        if not new_name:
            name_var.set(current_layer.name)
            messagebox.showerror("레이어 편집 실패", "레이어 이름은 비워 둘 수 없습니다.")
            return "break"
        name_var.set(new_name)
        self.status_var.set(f"레이어 이름 변경 대기: {new_name}")
        return "break"

    #endregion

    #region 진행 상태 표시

    def _show_progress_bar(self) -> None:
        """파일 로드나 내보내기 작업 중에만 진행 막대를 상태 문구 오른쪽에 표시합니다."""

        # 상태 메시지 오른쪽에 진행 막대 표시
        self.progress_bar.grid(row=0, column=1, sticky="e", padx=(12, 0))

    def _hide_progress_bar(self) -> None:
        """진행 막대를 숨겨 작업이 끝난 상태를 명확히 합니다."""

        # 진행 막대 숨김
        self.progress_bar.grid_remove()

    #endregion

    #region 내보내기 작업

    def _update_export_format_state(self) -> None:
        """로드된 문서 포맷과 Photoshop COM 상태에 따라 PSD 출력 선택 가능 여부를 갱신합니다."""

        # 현재 문서 포맷과 Photoshop COM 상태로 출력 형식 상태 계산
        document_format = self.document.format if self.document is not None else None
        state = resolve_export_format_state(
            document_format,
            self.psd_export_available,
            self.psd_export_message,
            self.format_var.get(),
        )

        # 계산된 출력 형식과 경고 메시지를 GUI 상태에 반영
        self.format_var.set(state.format_value)
        self.psd_export_warning_message = state.warning_message
        self.ase_radio.configure(state="normal" if state.ase_enabled else "disabled")
        if state.psd_enabled:
            self.psd_radio.configure(state="normal")
            return

        # PSD 출력을 사용할 수 없는 상태에서는 라디오 버튼 비활성화
        self.psd_radio.configure(state="disabled")

    def _create_export_job(self, selected_layer_ids: tuple[str, ...]) -> ExportJob:
        """현재 GUI 상태를 Exporter가 사용할 불변 작업 데이터로 변환합니다."""

        # 입력 파일 없는 경우 방어
        if self.source_path is None:
            raise DocumentBackendError("파일을 먼저 선택하세요.")
        # 현재 GUI 옵션을 ExportJob으로 변환
        # 재구성 모드는 GUI 비활성화 상태와 별개로 작업 데이터에서도 옵션을 강제 보정합니다.
        is_reconstruct = self.output_mode_var.get() == "reconstruct"
        return ExportJob(
            source_path=self.source_path,
            output_directory=Path(self.output_dir_var.get().strip() or self.source_path.parent),
            wrap_with_folder=False if is_reconstruct else self.wrap_var.get(),
            include_original_name=self.name_original_var.get(),
            include_layer_name=self.name_layer_var.get(),
            include_layer_count=self.name_layer_count_var.get() if is_reconstruct else False,
            include_date=self.name_date_var.get(),
            overwrite_existing=self.overwrite_existing_var.get(),
            export_format=self.format_var.get(),
            output_mode=self.output_mode_var.get(),
            rescale=self.rescale_var.get(),
            preserve_canvas=True if is_reconstruct else self.layer_bounds_var.get() == "preserve",
            selected_layer_ids=selected_layer_ids,
            layer_names={layer_id: var.get().strip() for layer_id, var in self.layer_name_vars.items()},
        )

    def _start_export(self) -> None:
        """내보내기 설정을 저장하고 백그라운드 스레드에서 Exporter를 실행합니다."""

        # 입력 파일 없는 경우 경고
        if self.source_path is None:
            messagebox.showwarning("파일 없음", "파일을 먼저 선택하세요.")
            return
        # 선택 레이어와 내보내기 작업 생성
        selected_layer_ids = self._current_selected_layer_ids()
        job = self._create_export_job(selected_layer_ids)
        # 설정 저장 및 진행 상태 초기화
        self._save_settings()
        self.progress_var.set(0)
        self._show_progress_bar()
        self.status_var.set("내보내는 중...")
        # 백그라운드 스레드 시작 및 결과 큐 polling 예약
        threading.Thread(target=self._run_export, args=(job,), daemon=True).start()
        self.root.after(100, self._poll_worker_queue)

    def _run_export(self, job: ExportJob) -> None:
        """GUI가 멈추지 않도록 실제 내보내기를 워커 스레드에서 수행합니다."""

        # 진행률 계산을 위한 카운터 준비
        progress_count = 0
        total_count = max(1, len(job.selected_layer_ids))

        # Exporter 진행 콜백을 Tkinter 메인 루프 큐 메시지로 변환
        def progress(message: str) -> None:
            nonlocal progress_count
            progress_count += 1
            # Tkinter 위젯은 메인 스레드에서만 갱신해야 하므로 queue로 메시지만 전달합니다.
            self.worker_queue.put(("progress", (progress_count, total_count, message)))

        # 내보내기 실행 결과를 큐로 전달
        try:
            outputs = Exporter(progress=progress).export(job)
        except Exception as exc:
            self.worker_queue.put(("error", exc))
        else:
            self.worker_queue.put(("done", outputs))

    def _poll_worker_queue(self) -> None:
        """워커 스레드가 보낸 진행/완료/오류 메시지를 Tkinter 메인 루프에서 처리합니다."""

        # 큐가 비어 있으면 잠시 뒤 다시 확인
        try:
            kind, payload = self.worker_queue.get_nowait()
        except queue.Empty:
            self.root.after(100, self._poll_worker_queue)
            return

        # 진행 메시지 처리
        if kind == "progress":
            current, total, message = payload
            self.progress_var.set(min(100, current / total * 100))
            self.status_var.set(f"{message} ({current}/{total})")
            self.root.after(100, self._poll_worker_queue)
        # 오류 메시지 처리
        elif kind == "error":
            self.progress_var.set(0)
            self._hide_progress_bar()
            self.status_var.set("내보내기에 실패했습니다.")
            messagebox.showerror("내보내기 실패", str(payload))
        # 완료 메시지 처리
        elif kind == "done":
            outputs = payload
            self.progress_var.set(100)
            self.status_var.set(f"내보내기 완료: 파일 {len(outputs)}개")
            messagebox.showinfo("내보내기 완료", f"파일 {len(outputs)}개를 내보냈습니다.")
            self._hide_progress_bar()

    #endregion

    #region 설정 저장 및 종료

    def _save_settings(self) -> None:
        """현재 GUI 옵션을 다음 실행 때 복원할 수 있도록 설정 파일에 저장합니다."""

        # 출력 관련 설정 저장
        self.settings.output_directory = self.output_dir_var.get().strip()
        self.settings.wrap_with_folder = self.wrap_var.get()
        self.settings.include_original_name = self.name_original_var.get()
        self.settings.include_layer_name = self.name_layer_var.get()
        self.settings.include_layer_count = self.name_layer_count_var.get()
        self.settings.include_date = self.name_date_var.get()
        self.settings.overwrite_existing = self.overwrite_existing_var.get()
        self.settings.export_format = self.format_var.get()
        self.settings.output_mode = self.output_mode_var.get()
        self.settings.rescale = self.rescale_var.get()
        self.settings.preserve_canvas = self.layer_bounds_var.get() == "preserve"
        self.settings.save()

    def _on_close(self) -> None:
        """창을 닫기 전에 사용자 설정을 저장합니다."""

        # 설정 저장 후 윈도우 종료
        self._save_settings()
        self.root.destroy()

    #endregion


def main() -> None:
    """드래그 앤 드롭 지원 여부에 맞는 루트 윈도우를 만들고 앱을 시작합니다."""

    root_class = TkinterDnD.Tk if TkinterDnD is not None else tk.Tk
    root = root_class()
    PsdDecomposerApp(root)
    root.mainloop()


class Tooltip:
    """라벨에 마우스를 올렸을 때 짧은 안내 문구를 띄우는 헬퍼입니다."""

    def __init__(self, widget: tk.Widget, text: str) -> None:
        """대상 위젯에 hover 이벤트를 연결합니다."""

        self.widget = widget
        self.text = text
        self.window: tk.Toplevel | None = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, _event=None) -> None:
        """위젯 아래쪽에 border가 있는 작은 툴팁 창을 생성합니다."""

        if self.window is not None:
            return
        x = self.widget.winfo_rootx() + 16
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
        self.window = tk.Toplevel(self.widget)
        self.window.wm_overrideredirect(True)
        self.window.wm_geometry(f"+{x}+{y}")
        label = ttk.Label(
            self.window,
            text=self.text,
            justify="left",
            padding=(8, 5),
            relief="solid",
            borderwidth=1,
        )
        label.pack()

    def _hide(self, _event=None) -> None:
        """마우스가 벗어나면 툴팁 창을 제거합니다."""

        if self.window is not None:
            self.window.destroy()
            self.window = None

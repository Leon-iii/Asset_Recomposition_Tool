from __future__ import annotations

import queue
import threading
import tkinter as tk
import sys
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from .config import AppSettings
from .document_backend import DocumentBackend, DocumentBackendError, SUPPORTED_EXTENSIONS, load_document, to_document_error
from .exporter import Exporter
from .models import ExportJob, LayerInfo


DROP_ZONE_HEIGHT = 122
DROP_ZONE_PADDING = 10
LAYER_TABLE_RIGHT_PADDING = 8


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

    def __init__(self, root: tk.Tk) -> None:
        """애플리케이션 상태 변수를 준비하고 전체 GUI를 구성합니다."""

        self.root = root
        self.root.title("PSD Decomposition Tool v1.0")
        self._set_window_icon()
        self.root.minsize(820, 760)

        self.settings = AppSettings.load()
        self.document: DocumentBackend | None = None
        self.source_path: Path | None = None
        self.layer_vars: dict[str, tk.BooleanVar] = {}
        self.layer_photos: list[ImageTk.PhotoImage] = []
        self.preview_photo: ImageTk.PhotoImage | None = None
        self.select_all_check: ttk.Checkbutton | None = None
        self.is_updating_layer_selection = False
        self.worker_queue: queue.Queue[tuple[str, object]] = queue.Queue()

        self.source_var = tk.StringVar()
        self.output_dir_var = tk.StringVar(value=self.settings.output_directory)
        self.wrap_var = tk.BooleanVar(value=self.settings.wrap_with_folder)
        self.name_original_var = tk.BooleanVar(value=self.settings.include_original_name)
        self.name_layer_var = tk.BooleanVar(value=self.settings.include_layer_name)
        self.name_date_var = tk.BooleanVar(value=self.settings.include_date)
        self.overwrite_existing_var = tk.BooleanVar(value=self.settings.overwrite_existing)
        self.psd_export_available, self.psd_export_message = self._detect_psd_export_status()
        if self.settings.export_format == "PSD" and not self.psd_export_available:
            self.settings.export_format = "PNG"
        self.format_var = tk.StringVar(value=self.settings.export_format)
        self.rescale_var = tk.IntVar(value=self.settings.rescale)
        self.layer_bounds_var = tk.StringVar(value="preserve" if self.settings.preserve_canvas else "crop")
        self.select_all_var = tk.BooleanVar(value=False)
        self.progress_var = tk.DoubleVar(value=0)
        self.status_var = tk.StringVar(value="PSD 또는 Aseprite 파일을 선택하거나 드래그 앤 드롭하세요.")

        self._build_ui()
        self._bind_drag_and_drop()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _set_window_icon(self) -> None:
        """실행 환경에 맞는 assets/app.ico를 찾아 Tkinter 창 아이콘으로 설정합니다."""

        icon_path = resource_path("assets/app.ico")
        if icon_path.exists():
            self.root.iconbitmap(str(icon_path))

    def _build_ui(self) -> None:
        """파일 입력, 경로, 레이어 테이블, 출력 설정, 상태 표시 영역을 배치합니다."""

        self.style = ttk.Style(self.root)
        self.style.configure("Status.Horizontal.TProgressbar", thickness=15)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)

        input_frame = ttk.LabelFrame(self.root, text="파일 입력", padding=12)
        input_frame.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))
        input_frame.columnconfigure(0, weight=1)

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

        ttk.Label(path_frame, text="입력 파일").grid(row=0, column=0, sticky="w")
        ttk.Entry(path_frame, textvariable=self.source_var, state="readonly").grid(row=0, column=1, sticky="ew", padx=(8, 0))
        ttk.Button(path_frame, text="파일 찾기...", command=self._browse_file).grid(row=0, column=2, padx=(8, 0))

        output_dir_label = ttk.Label(path_frame, text="출력 폴더")
        output_dir_label.grid(row=1, column=0, sticky="w", pady=(8, 0))
        Tooltip(output_dir_label, "분리한 레이어 파일을 저장할 폴더입니다.\n파일이 로드되면 원본 파일이 있는 폴더로 갱신됩니다.")
        ttk.Entry(path_frame, textvariable=self.output_dir_var).grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(8, 0))
        ttk.Button(path_frame, text="경로 찾기...", command=self._browse_output_dir).grid(row=1, column=2, padx=(8, 0), pady=(8, 0))

        body = ttk.Frame(self.root)
        body.grid(row=2, column=0, sticky="nsew", padx=12)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        layer_frame = ttk.LabelFrame(body, text="레이어 선택", padding=12)
        layer_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        layer_frame.columnconfigure(0, weight=1)
        layer_frame.rowconfigure(1, weight=1)
        toolbar = ttk.Frame(layer_frame)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        canvas = tk.Canvas(layer_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(layer_frame, orient="vertical", command=canvas.yview)
        self.layer_list = ttk.Frame(canvas)
        self.layer_list.columnconfigure(2, weight=1)
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

        # 출력 설정 영역은 내보내기 버튼이 항상 하단에 머물도록 row weight를 둡니다.
        settings_frame = ttk.LabelFrame(body, text="출력 설정", padding=12)
        settings_frame.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        settings_frame.columnconfigure(1, weight=1)
        settings_frame.rowconfigure(7, weight=1)

        file_options_frame = ttk.Frame(settings_frame)
        file_options_frame.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 12))
        wrap_check = ttk.Checkbutton(file_options_frame, variable=self.wrap_var)
        wrap_check.pack(side="left")
        wrap_label = ttk.Label(file_options_frame, text="하위 폴더로 묶기")
        wrap_label.pack(side="left", padx=(6, 0))
        Tooltip(wrap_label, '내보낸 파일을 "(원본 파일명)_decomposed" 하위 폴더 안에 저장합니다.')

        ttk.Checkbutton(file_options_frame, variable=self.overwrite_existing_var).pack(side="left", padx=(24, 0))
        overwrite_label = ttk.Label(file_options_frame, text="기존 출력물 삭제")
        overwrite_label.pack(side="left", padx=(6, 0))
        Tooltip(overwrite_label, "저장할 파일명과 같은 기존 파일이 있으면 덮어씁니다.\n같은 배치에서 새로 만든 파일끼리는 덮어쓰지 않습니다.")
        ttk.Separator(settings_frame, orient="horizontal").grid(row=1, column=0, columnspan=3, sticky="ew", pady=(0, 14))

        file_name_label = ttk.Label(settings_frame, text="파일 이름")
        file_name_label.grid(row=2, column=0, sticky="w")
        Tooltip(file_name_label, "내보낼 파일명에 포함할 항목입니다.\n여러 항목을 선택하면 언더스코어로 이어 붙입니다.")
        name_frame = ttk.Frame(settings_frame)
        name_frame.grid(row=2, column=1, columnspan=2, sticky="w", padx=(8, 0))
        ttk.Checkbutton(name_frame, text="원본 파일명", variable=self.name_original_var).pack(side="left")
        ttk.Checkbutton(name_frame, text="레이어명", variable=self.name_layer_var).pack(side="left", padx=(8, 0))
        ttk.Checkbutton(name_frame, text="날짜", variable=self.name_date_var).pack(side="left", padx=(8, 0))

        export_format_label = ttk.Label(settings_frame, text="출력 형식")
        export_format_label.grid(row=3, column=0, sticky="w", pady=(14, 0))
        Tooltip(export_format_label, "PSD 또는 PNG로 저장합니다.\nPSD 저장은 Windows Photoshop 자동화가 필요합니다.")
        format_frame = ttk.Frame(settings_frame)
        format_frame.grid(row=3, column=1, columnspan=2, sticky="w", padx=(8, 0), pady=(14, 0))
        self.psd_radio = ttk.Radiobutton(format_frame, text="PSD", variable=self.format_var, value="PSD")
        self.psd_radio.pack(side="left")
        if not self.psd_export_available:
            self.psd_radio.configure(state="disabled")
            self.psd_radio.bind("<Button-1>", self._show_psd_unavailable_warning)
        ttk.Radiobutton(format_frame, text="PNG", variable=self.format_var, value="PNG").pack(side="left", padx=(12, 0))

        rescale_label = ttk.Label(settings_frame, text="확대 비율")
        rescale_label.grid(row=4, column=0, sticky="w", pady=(14, 0))
        Tooltip(rescale_label, "저장할 이미지 크기 배율입니다.\n100%는 원본 크기 그대로 저장합니다.")
        rescale_frame = ttk.Frame(settings_frame)
        rescale_frame.grid(row=4, column=1, columnspan=2, sticky="w", padx=(8, 0), pady=(14, 0))
        for value in (100, 200, 400, 800):
            ttk.Radiobutton(rescale_frame, text=f"{value}%", variable=self.rescale_var, value=value).pack(side="left", padx=(0, 10))

        layer_bounds_label = ttk.Label(settings_frame, text="레이어 영역")
        layer_bounds_label.grid(row=5, column=0, sticky="w", pady=(14, 0))
        Tooltip(layer_bounds_label, "원본 캔버스 위치를 유지하거나,\n레이어 오브젝트 영역만 잘라 저장할지 선택합니다.")
        bounds_frame = ttk.Frame(settings_frame)
        bounds_frame.grid(row=5, column=1, columnspan=2, sticky="w", padx=(8, 0), pady=(14, 0))
        ttk.Radiobutton(
            bounds_frame,
            text="원본 캔버스와 위치 유지",
            variable=self.layer_bounds_var,
            value="preserve",
        ).pack(anchor="w")
        ttk.Radiobutton(
            bounds_frame,
            text="레이어 오브젝트만 크롭",
            variable=self.layer_bounds_var,
            value="crop",
        ).pack(anchor="w")

        self.export_button = ttk.Button(
            settings_frame,
            text="선택한 레이어 내보내기",
            command=self._start_export,
            state="disabled",
        )
        self.export_button.grid(
            row=7, column=0, columnspan=3, sticky="sew", pady=(24, 0)
        )

        status_frame = ttk.Frame(self.root)
        status_frame.grid(row=3, column=0, sticky="ew", padx=12, pady=12)
        status_frame.columnconfigure(0, weight=1)
        ttk.Label(status_frame, textvariable=self.status_var, anchor="w").grid(row=0, column=0, sticky="ew")
        self.progress_bar = ttk.Progressbar(
            status_frame,
            variable=self.progress_var,
            maximum=100,
            length=300,
            style="Status.Horizontal.TProgressbar",
        )

    def _bind_drag_and_drop(self) -> None:
        """드롭 존과 내부 라벨에 동일한 파일 드롭 이벤트를 연결합니다."""

        if TkinterDnD is None or DND_FILES is None:
            message = "드래그 앤 드롭을 사용하려면 tkinterdnd2가 필요합니다."
            if TKINTERDND_IMPORT_ERROR is not None:
                message = f"{message}\n감지된 오류: {TKINTERDND_IMPORT_ERROR}"
            self.drop_detail_label.configure(text=message)
            self.drop_placeholder.configure(text=f"{message}\n파일 찾기 버튼을 사용하세요.")
            return

        # Windows의 tkinterdnd2는 마우스 아래의 실제 하위 위젯에 따라 Drop 이벤트가 달라질 수 있습니다.
        # 루트와 드롭 존 전체에 함께 등록해 placeholder/썸네일/라벨 위에서도 같은 핸들러가 호출되게 합니다.
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

    def _detect_psd_export_status(self) -> tuple[bool, str]:
        """PSD 저장에 필요한 pywin32와 Photoshop COM 등록 상태를 확인합니다."""

        try:
            import win32com.client  # noqa: F401
        except ImportError:
            return False, "PSD 저장에는 pywin32와 설치된 Photoshop이 필요합니다."

        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"Photoshop.Application\CLSID"):
                return True, "PSD 저장 가능"
        except OSError:
            return False, "Photoshop COM 등록을 찾을 수 없습니다. Photoshop 설치 상태를 확인하세요."

    def _show_psd_unavailable_warning(self, _event=None) -> str:
        """비활성화된 PSD 라디오 버튼을 눌렀을 때 사유를 알려줍니다."""

        messagebox.showwarning("PSD 저장 불가", self.psd_export_message)
        return "break"

    def _browse_file(self) -> None:
        """파일 선택 대화상자에서 지원 문서를 선택해 로드합니다."""

        filetypes = [
            ("지원 파일", "*.psd *.ase *.aseprite"),
            ("PSD 파일", "*.psd"),
            ("Aseprite 파일", "*.ase *.aseprite"),
            ("모든 파일", "*.*"),
        ]
        selected = filedialog.askopenfilename(title="파일 열기", filetypes=filetypes)
        if selected:
            self._load_file(Path(selected))

    def _browse_output_dir(self) -> None:
        """출력 폴더 선택 대화상자를 열고 선택값을 반영합니다."""

        selected = filedialog.askdirectory(title="출력 폴더 선택")
        if selected:
            self.output_dir_var.set(selected)

    def _handle_drop(self, event) -> None:
        """드롭된 파일 목록 중 첫 번째 파일을 입력 문서로 처리합니다."""

        paths = self.root.tk.splitlist(event.data)
        if paths:
            self._load_file(Path(paths[0]))

    def _load_file(self, path: Path) -> None:
        """지원 문서를 열고 미리보기, 출력 폴더, 레이어 테이블을 갱신합니다."""

        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            # 잘못된 확장자는 기존에 로드된 파일 상태를 유지한 채 경고만 표시합니다.
            supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
            messagebox.showwarning("지원하지 않는 파일", f"지원 형식: {supported}")
            return
        previous_status = self.status_var.get()
        previous_placeholder_text = self.drop_placeholder.cget("text")
        had_loaded_file = self.source_path is not None
        self._show_file_processing_message()
        try:
            document = load_document(path)
            preview_image = document.render_preview()
        except Exception as exc:
            self._restore_drop_zone_after_failed_load(had_loaded_file, previous_placeholder_text, previous_status)
            messagebox.showerror("파일 열기 실패", str(to_document_error(exc)))
            return

        self.document = document
        self.source_path = path
        self.source_var.set(str(path))
        # 새 파일을 열면 출력 폴더도 해당 원본 파일이 있는 폴더로 자동 동기화합니다.
        self.output_dir_var.set(str(path.parent))
        self._update_drop_zone(path, preview_image)
        self._populate_layers(self.document.layers)
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

        self.progress_var.set(0)
        self._hide_progress_bar()
        self.status_var.set(status_text)
        if had_loaded_file:
            self.drop_placeholder.grid_remove()
            self.drop_image_label.grid(row=0, column=0, rowspan=2, sticky="nsw")
            self.drop_title_label.grid(row=0, column=1, sticky="sew", padx=(10, 0))
            self.drop_detail_label.grid(row=1, column=1, sticky="new", padx=(10, 0), pady=(4, 0))
            return

        self.drop_image_label.grid_remove()
        self.drop_title_label.grid_remove()
        self.drop_detail_label.grid_remove()
        self.drop_placeholder.configure(text=placeholder_text)
        self.drop_placeholder.grid(row=0, column=0, rowspan=2, columnspan=2, sticky="nsew")

    def _show_file_processing_message(self) -> None:
        """파일 로드가 시작되었음을 드롭 존과 하단 상태 영역에 즉시 표시합니다."""

        self.drop_image_label.grid_remove()
        self.drop_title_label.grid_remove()
        self.drop_detail_label.grid_remove()
        self.drop_placeholder.configure(text="파일 처리 중...")
        self.drop_placeholder.grid(row=0, column=0, rowspan=2, columnspan=2, sticky="nsew")
        self.progress_var.set(0)
        self._show_progress_bar()
        self.status_var.set("파일 처리 중...")
        self.root.update_idletasks()

    def _update_drop_zone(self, path: Path, preview_image: Image.Image) -> None:
        """드롭 존을 안내 문구에서 파일 썸네일과 파일 정보 표시로 전환합니다."""

        self.drop_placeholder.grid_remove()
        self.drop_zone.rowconfigure(0, weight=1)
        self.drop_zone.rowconfigure(1, weight=1)
        self.drop_image_label.grid(row=0, column=0, rowspan=2, sticky="nsw")
        self.drop_title_label.grid(row=0, column=1, sticky="sew", padx=(10, 0))
        self.drop_detail_label.grid(row=1, column=1, sticky="new", padx=(10, 0), pady=(4, 0))
        thumbnail = preview_image.convert("RGBA")
        thumbnail.thumbnail(self._drop_zone_thumbnail_size())
        self.preview_photo = ImageTk.PhotoImage(thumbnail)
        self.drop_image_label.configure(image=self.preview_photo)
        self.drop_title_label.configure(text=f"{path.stem}{path.suffix}")
        self.drop_detail_label.configure(text=f"캔버스 크기: {preview_image.width}x{preview_image.height} px")

    def _drop_zone_thumbnail_size(self) -> tuple[int, int]:
        """현재 드롭 존 높이에 맞춰 원본 파일 썸네일의 최대 크기를 계산합니다."""

        self.drop_zone.update_idletasks()
        height = self.drop_zone.winfo_height()
        if height <= 1:
            height = DROP_ZONE_HEIGHT
        max_height = max(48, height - DROP_ZONE_PADDING * 2)
        max_width = round(max_height * 1.5)
        return max_width, max_height

    def _populate_layers(self, layers: tuple[LayerInfo, ...]) -> None:
        """레이어 메타데이터로 선택 체크박스, 썸네일, 이름 테이블을 다시 만듭니다."""

        for child in self.layer_list.winfo_children():
            child.destroy()
        self.select_all_check = None
        self.layer_vars.clear()
        self.layer_photos.clear()

        if not layers:
            ttk.Label(self.layer_list, text="내보낼 수 있는 레이어가 없습니다.").pack(anchor="w")
            self._update_layer_selection_state()
            return

        assert self.document is not None
        self.select_all_check = ttk.Checkbutton(
            self.layer_list,
            variable=self.select_all_var,
            command=self._toggle_select_all,
            state="disabled",
        )
        self.select_all_check.grid(row=0, column=0, sticky="", padx=(0, 8), pady=(0, 6))
        ttk.Label(self.layer_list, text="미리보기", anchor="center").grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=(0, 6))
        ttk.Label(self.layer_list, text="레이어 이름", anchor="w").grid(row=0, column=2, sticky="ew", pady=(0, 6))
        ttk.Separator(self.layer_list, orient="horizontal").grid(row=1, column=0, columnspan=3, sticky="ew", pady=(0, 4))

        for index, layer in enumerate(layers):
            row = 2 + index * 2
            var = tk.BooleanVar(value=layer.visible)
            self.layer_vars[layer.id] = var
            label = layer.display_name
            if layer.width and layer.height:
                label = f"{label} ({layer.width}x{layer.height})"

            photo = self._create_layer_photo(layer.id)
            self.layer_photos.append(photo)
            # 모든 행을 같은 최소 높이로 고정해 체크박스와 썸네일이 흔들리지 않게 합니다.
            self.layer_list.rowconfigure(row, minsize=56)
            ttk.Checkbutton(
                self.layer_list,
                variable=var,
                command=self._on_layer_selection_changed,
            ).grid(row=row, column=0, sticky="", padx=(0, 8), pady=4)
            ttk.Label(self.layer_list, image=photo, anchor="center").grid(row=row, column=1, sticky="", padx=(0, 8), pady=4)
            ttk.Label(self.layer_list, text=label, anchor="w").grid(row=row, column=2, sticky="ew", pady=4)
            ttk.Separator(self.layer_list, orient="horizontal").grid(row=row + 1, column=0, columnspan=3, sticky="ew", pady=(0, 1))
        self._update_layer_selection_state()

    def _create_layer_photo(self, layer_id: str) -> ImageTk.PhotoImage:
        """레이어 썸네일을 만들고, 실패 시 투명 이미지로 테이블 레이아웃을 유지합니다."""

        assert self.document is not None
        try:
            thumbnail = self.document.render_layer_thumbnail(layer_id)
        except DocumentBackendError:
            thumbnail = Image.new("RGBA", (48, 48), (0, 0, 0, 0))
        return ImageTk.PhotoImage(thumbnail)

    def _set_all_layers(self, selected: bool) -> None:
        """전체 선택 체크박스에서 개별 레이어 체크 상태를 일괄 변경합니다."""

        self.is_updating_layer_selection = True
        for var in self.layer_vars.values():
            var.set(selected)
        self.is_updating_layer_selection = False
        self._update_layer_selection_state()

    def _toggle_select_all(self) -> None:
        """전체 선택 체크박스의 true/false/alternate 상태를 개별 체크박스에 전파합니다."""

        if self.is_updating_layer_selection:
            return
        if "alternate" in self.select_all_check.state():
            self._set_all_layers(True)
        elif self.select_all_var.get():
            self._set_all_layers(True)
        else:
            self._set_all_layers(False)

    def _on_layer_selection_changed(self) -> None:
        """개별 레이어 선택 변경을 전체 선택 상태와 내보내기 버튼 상태에 반영합니다."""

        if not self.is_updating_layer_selection:
            self._update_layer_selection_state()

    def _update_layer_selection_state(self) -> None:
        """선택 개수를 기준으로 전체 선택의 alternate 상태와 버튼 활성화를 계산합니다."""

        selected_count = sum(1 for var in self.layer_vars.values() if var.get())
        total_count = len(self.layer_vars)
        control_state = "normal" if total_count > 0 else "disabled"

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

        self.export_button.configure(state="normal" if selected_count > 0 else "disabled")

    def _current_selected_layer_ids(self) -> tuple[str, ...]:
        """현재 체크된 레이어 id만 내보내기 순서대로 반환합니다."""

        return tuple(layer_id for layer_id, var in self.layer_vars.items() if var.get())

    def _show_progress_bar(self) -> None:
        """파일 로드나 내보내기 작업 중에만 진행 막대를 상태 문구 오른쪽에 표시합니다."""

        self.progress_bar.grid(row=0, column=1, sticky="e", padx=(12, 0))

    def _hide_progress_bar(self) -> None:
        """진행 막대를 숨겨 작업이 끝난 상태를 명확히 합니다."""

        self.progress_bar.grid_remove()

    def _create_export_job(self, selected_layer_ids: tuple[str, ...]) -> ExportJob:
        """현재 GUI 상태를 Exporter가 사용할 불변 작업 데이터로 변환합니다."""

        if self.source_path is None:
            raise DocumentBackendError("파일을 먼저 선택하세요.")
        return ExportJob(
            source_path=self.source_path,
            output_directory=Path(self.output_dir_var.get().strip() or self.source_path.parent),
            wrap_with_folder=self.wrap_var.get(),
            include_original_name=self.name_original_var.get(),
            include_layer_name=self.name_layer_var.get(),
            include_date=self.name_date_var.get(),
            overwrite_existing=self.overwrite_existing_var.get(),
            export_format=self.format_var.get(),
            rescale=self.rescale_var.get(),
            preserve_canvas=self.layer_bounds_var.get() == "preserve",
            selected_layer_ids=selected_layer_ids,
        )

    def _start_export(self) -> None:
        """내보내기 설정을 저장하고 백그라운드 스레드에서 Exporter를 실행합니다."""

        if self.source_path is None:
            messagebox.showwarning("파일 없음", "파일을 먼저 선택하세요.")
            return
        selected_layer_ids = self._current_selected_layer_ids()
        job = self._create_export_job(selected_layer_ids)
        self._save_settings()
        self.progress_var.set(0)
        self._show_progress_bar()
        self.status_var.set("내보내는 중...")
        threading.Thread(target=self._run_export, args=(job,), daemon=True).start()
        self.root.after(100, self._poll_worker_queue)

    def _run_export(self, job: ExportJob) -> None:
        """GUI가 멈추지 않도록 실제 내보내기를 워커 스레드에서 수행합니다."""

        progress_count = 0
        total_count = max(1, len(job.selected_layer_ids))

        def progress(message: str) -> None:
            nonlocal progress_count
            progress_count += 1
            # Tkinter 위젯은 메인 스레드에서만 갱신해야 하므로 queue로 메시지만 전달합니다.
            self.worker_queue.put(("progress", (progress_count, total_count, message)))

        try:
            outputs = Exporter(progress=progress).export(job)
        except Exception as exc:
            self.worker_queue.put(("error", exc))
        else:
            self.worker_queue.put(("done", outputs))

    def _poll_worker_queue(self) -> None:
        """워커 스레드가 보낸 진행/완료/오류 메시지를 Tkinter 메인 루프에서 처리합니다."""

        try:
            kind, payload = self.worker_queue.get_nowait()
        except queue.Empty:
            self.root.after(100, self._poll_worker_queue)
            return

        if kind == "progress":
            current, total, message = payload
            self.progress_var.set(min(100, current / total * 100))
            self.status_var.set(f"{message} ({current}/{total})")
            self.root.after(100, self._poll_worker_queue)
        elif kind == "error":
            self.progress_var.set(0)
            self._hide_progress_bar()
            self.status_var.set("내보내기에 실패했습니다.")
            messagebox.showerror("내보내기 실패", str(payload))
        elif kind == "done":
            outputs = payload
            self.progress_var.set(100)
            self.status_var.set(f"내보내기 완료: 파일 {len(outputs)}개")
            messagebox.showinfo("내보내기 완료", f"파일 {len(outputs)}개를 내보냈습니다.")
            self._hide_progress_bar()

    def _save_settings(self) -> None:
        """현재 GUI 옵션을 다음 실행 때 복원할 수 있도록 설정 파일에 저장합니다."""

        self.settings.output_directory = self.output_dir_var.get().strip()
        self.settings.wrap_with_folder = self.wrap_var.get()
        self.settings.include_original_name = self.name_original_var.get()
        self.settings.include_layer_name = self.name_layer_var.get()
        self.settings.include_date = self.name_date_var.get()
        self.settings.overwrite_existing = self.overwrite_existing_var.get()
        self.settings.export_format = self.format_var.get()
        self.settings.rescale = self.rescale_var.get()
        self.settings.preserve_canvas = self.layer_bounds_var.get() == "preserve"
        self.settings.save()

    def _on_close(self) -> None:
        """창을 닫기 전에 사용자 설정을 저장합니다."""

        self._save_settings()
        self.root.destroy()


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

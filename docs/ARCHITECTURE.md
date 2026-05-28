# PSD Decomposition Tool 실행 흐름 설명

이 문서는 `specs.md`의 요구 계층과 현재 `psd_decomposer` 패키지 구현을 함께 기준으로, 프로그램이 어떤 클래스와 메서드를 거쳐 데이터를 처리하는지 추적한다.

## 계층 개요

`specs.md`는 프로그램을 다음 네 계층으로 나눈다.

1. 파일 입력 계층
2. 레이어 선택 계층
3. 출력 설정 계층
4. 처리 계층

현재 구현에서는 이 계층들이 아래 모듈로 분리되어 있다.

| 계층 | 주요 모듈 | 주요 클래스/함수 | 역할 |
| --- | --- | --- | --- |
| 파일 입력 계층 | `psd_decomposer.gui`, `psd_decomposer.psd_backend` | `PsdDecomposerApp`, `PsdDocument`, `validate_input_path` | PSD 선택, 드래그 앤 드롭, 파일 검증, PSD 로드 |
| 레이어 선택 계층 | `psd_decomposer.gui`, `psd_decomposer.models`, `psd_decomposer.psd_backend` | `LayerInfo`, `PsdDocument._collect_layers`, `PsdDecomposerApp._populate_layers` | PSD 레이어 목록 구성, 썸네일 생성, 선택 상태 관리 |
| 출력 설정 계층 | `psd_decomposer.gui`, `psd_decomposer.config`, `psd_decomposer.models` | `AppSettings`, `ExportJob`, `PsdDecomposerApp._create_export_job` | GUI 옵션 저장/복원, 내보내기 작업 데이터 생성 |
| 처리 계층 | `psd_decomposer.exporter`, `psd_decomposer.naming`, `psd_decomposer.psd_backend` | `Exporter`, `build_base_name`, `resolve_output_path`, `PsdDocument.render_layer` | 선택 레이어를 PNG 또는 PSD로 저장 |

## 주요 데이터 객체

### `LayerInfo`

위치: `psd_decomposer.models`

PSD의 한 아트 레이어를 GUI와 Exporter가 공통으로 이해할 수 있게 만든 불변 데이터 객체다.

주요 필드:

- `id`: PSD 순회 순서 기반 레이어 id
- `name`: 레이어 이름
- `path`: 상위 그룹 이름 tuple
- `visible`: PSD에서의 표시 여부
- `width`, `height`: 레이어 bbox 크기
- `left`, `top`: 원본 캔버스에서의 레이어 위치

주요 메서드:

- `LayerInfo.display_name`: `path`와 `name`을 `" / "`로 연결해 GUI 표시와 출력 로그에 사용한다.

### `ExportJob`

위치: `psd_decomposer.models`

GUI에서 선택한 모든 내보내기 옵션을 Exporter로 넘기기 위한 불변 데이터 객체다.

주요 필드:

- `source_path`: 원본 PSD 경로
- `output_directory`: 출력 폴더
- `wrap_with_folder`: 하위 폴더로 묶기 여부
- `include_original_name`, `include_layer_name`, `include_date`: 파일명 구성 옵션
- `overwrite_existing`: 기존 출력물 덮어쓰기 여부
- `export_format`: `PNG` 또는 `PSD`
- `rescale`: 출력 배율
- `preserve_canvas`: 원본 캔버스와 위치 보존 여부
- `selected_layer_ids`: 내보낼 레이어 id 목록

### `AppSettings`

위치: `psd_decomposer.config`

프로그램 종료 전 GUI 옵션을 JSON으로 저장하고, 다음 실행 시 복원한다.

주요 메서드:

- `AppSettings.load`: 설정 파일을 읽고 잘못된 값은 기본값으로 복구한다.
- `AppSettings.save`: 현재 설정을 `~/.psd_decomposition_tool/settings.json`에 저장한다.

## 1. 프로그램 시작 흐름

진입점은 두 가지가 있다.

1. `main.py`
2. `python -m psd_decomposer`

둘 다 최종적으로 `psd_decomposer.gui.main`을 호출한다.

흐름:

1. `gui.main`
2. `TkinterDnD.Tk` 또는 `tk.Tk` 생성
3. `PsdDecomposerApp.__init__`
4. `PsdDecomposerApp._set_window_icon`
5. `AppSettings.load`
6. `PsdDecomposerApp._build_ui`
7. `PsdDecomposerApp._bind_drag_and_drop`
8. `root.mainloop`

### 리소스 로드

아이콘 같은 리소스는 `resource_path`와 `resource_base_paths`가 찾는다.

`resource_base_paths`는 다음 실행 환경을 모두 고려한다.

- PyInstaller의 `_MEIPASS`
- 빌드된 exe가 있는 폴더
- 빌드 내부 `_internal` 폴더
- 개발 실행 시 프로젝트 루트

이 흐름 덕분에 `uv run python main.py`와 빌드된 exe 모두에서 `assets/app.ico`를 찾을 수 있다.

## 2. 파일 입력 계층

파일 입력은 파일 찾기 버튼과 드래그 앤 드롭 두 경로를 지원한다.

### 파일 찾기 흐름

1. 사용자가 파일 찾기 버튼 클릭
2. `PsdDecomposerApp._browse_file`
3. `filedialog.askopenfilename`
4. 선택된 경로를 `Path`로 변환
5. `PsdDecomposerApp._load_file`

### 드래그 앤 드롭 흐름

1. `PsdDecomposerApp._bind_drag_and_drop`
2. 드롭 존 관련 위젯에 `drop_target_register`
3. 사용자가 파일 드롭
4. `PsdDecomposerApp._handle_drop`
5. `root.tk.splitlist(event.data)`로 드롭 경로 파싱
6. 첫 번째 경로를 `PsdDecomposerApp._load_file`로 전달

`tkinterdnd2`가 설치되지 않은 경우에는 드래그 앤 드롭만 비활성화되고, 파일 찾기 버튼은 계속 사용할 수 있다.

### PSD 로드 흐름

핵심 메서드는 `PsdDecomposerApp._load_file`이다.

흐름:

1. 확장자 검사
   - `SUPPORTED_EXTENSIONS`에 없는 확장자는 거부한다.
   - 이때 기존에 로드된 파일 상태는 유지한다.
2. `PsdDecomposerApp._show_file_processing_message`
   - 드롭 존 문구를 "파일 처리 중..." 상태로 바꾼다.
   - 하단 progress bar를 표시한다.
3. `PsdDocument(path)` 생성
4. `PsdDocument.__init__`
5. `validate_input_path`
6. `psd_tools.PSDImage.open`
7. `PsdDocument._get_canvas_size`
8. `PsdDocument._collect_layers`
9. `PsdDocument.render_preview`
10. GUI 상태 갱신
    - `source_path`
    - `source_var`
    - `output_dir_var`
11. `PsdDecomposerApp._update_drop_zone`
12. `PsdDecomposerApp._populate_layers`

### 드롭 존 표시 흐름

`PsdDecomposerApp._update_drop_zone`은 로드된 원본 파일 정보를 드롭 존에 표시한다.

사용하는 값:

- `path.stem`
- `path.suffix`
- `preview_image.width`
- `preview_image.height`
- `PsdDecomposerApp._drop_zone_thumbnail_size`

`_drop_zone_thumbnail_size`는 현재 드롭 존 높이에서 padding을 뺀 값을 기준으로 썸네일 최대 높이와 너비를 계산한다.

## 3. 레이어 선택 계층

레이어 목록은 `PsdDocument._collect_layers`에서 만들어지고, GUI 테이블은 `PsdDecomposerApp._populate_layers`에서 구성된다.

### 레이어 수집 흐름

1. `PsdDocument.__init__`
2. `PsdDocument._collect_layers`
3. 내부 재귀 함수 `walk`
4. PSD 노드 순회
5. 그룹이면 `group_path`에 그룹명을 누적하고 하위 노드로 진입
6. 아트 레이어이면 bbox를 읽어 `LayerInfo` 생성
7. `self.layers`에 tuple로 저장
8. `self._layers_by_id` 캐시 생성

`LayerInfo.id`는 현재 PSD 순회 순서를 문자열로 만든 값이다. 같은 id는 나중에 `PsdDocument.get_layer_node`가 실제 psd-tools 노드를 다시 찾을 때 사용한다.

### 레이어 테이블 구성 흐름

1. `PsdDecomposerApp._populate_layers(layers)`
2. 기존 테이블 위젯 제거
3. `layer_vars`와 `layer_photos` 초기화
4. 전체 선택 체크박스 생성
5. 헤더 생성
   - 전체 선택 체크박스
   - 미리보기
   - 레이어 이름
6. 각 레이어 행 생성
   - `tk.BooleanVar(value=layer.visible)`
   - `PsdDecomposerApp._create_layer_photo`
   - 개별 `ttk.Checkbutton`
   - 썸네일 `ttk.Label`
   - 레이어 이름 `ttk.Label`
   - 행 separator
7. `PsdDecomposerApp._update_layer_selection_state`

### 레이어 썸네일 흐름

1. `PsdDecomposerApp._create_layer_photo(layer_id)`
2. `PsdDocument.render_layer_thumbnail(layer_id)`
3. `PsdDocument.render_layer(layer_id)`
4. `PsdDocument.get_layer_node(layer_id)`
5. `node.composite`
6. `Image.thumbnail`
7. `ImageTk.PhotoImage`

렌더링 실패 시에는 투명 이미지가 대신 들어가므로 테이블 레이아웃이 깨지지 않는다.

### 전체 선택 상태 흐름

관련 메서드:

- `PsdDecomposerApp._set_all_layers`
- `PsdDecomposerApp._toggle_select_all`
- `PsdDecomposerApp._on_layer_selection_changed`
- `PsdDecomposerApp._update_layer_selection_state`
- `PsdDecomposerApp._current_selected_layer_ids`

상태 규칙:

- 모든 레이어 선택: 전체 선택 체크박스 `true`
- 모든 레이어 해제: 전체 선택 체크박스 `false`
- 일부만 선택: 전체 선택 체크박스 `alternate`
- 선택된 레이어 0개: 내보내기 버튼 비활성화
- 선택된 레이어 1개 이상: 내보내기 버튼 활성화

`is_updating_layer_selection`은 전체 선택에서 개별 체크박스를 일괄 변경할 때 이벤트가 다시 역전파되는 것을 막기 위한 플래그다.

## 4. 출력 설정 계층

출력 설정은 `PsdDecomposerApp`의 Tkinter 변수에 저장되어 있다가 내보내기 직전에 `ExportJob`으로 변환된다.

### GUI 변수와 ExportJob 매핑

| GUI 변수 | ExportJob 필드 | 의미 |
| --- | --- | --- |
| `source_path` | `source_path` | 원본 PSD 경로 |
| `output_dir_var` | `output_directory` | 출력 폴더 |
| `wrap_var` | `wrap_with_folder` | 하위 폴더로 묶기 |
| `name_original_var` | `include_original_name` | 파일명에 원본명 포함 |
| `name_layer_var` | `include_layer_name` | 파일명에 레이어명 포함 |
| `name_date_var` | `include_date` | 파일명에 날짜 포함 |
| `overwrite_existing_var` | `overwrite_existing` | 기존 출력물 덮어쓰기 |
| `format_var` | `export_format` | PNG 또는 PSD |
| `rescale_var` | `rescale` | 100, 200, 400, 800% |
| `layer_bounds_var` | `preserve_canvas` | 원본 캔버스 보존 또는 레이어 crop |
| `layer_vars` | `selected_layer_ids` | 선택된 레이어 id 목록 |

### ExportJob 생성 흐름

1. 사용자가 선택한 레이어 내보내기 클릭
2. `PsdDecomposerApp._start_export`
3. `PsdDecomposerApp._current_selected_layer_ids`
4. `PsdDecomposerApp._create_export_job`
5. `ExportJob(...)` 생성

`layer_bounds_var` 값이 `"preserve"`이면 `preserve_canvas=True`, `"crop"`이면 `False`가 된다.

### 설정 저장 흐름

내보내기 직전과 창 종료 시 설정을 저장한다.

흐름:

1. `PsdDecomposerApp._save_settings`
2. `AppSettings` 필드 갱신
3. `AppSettings.save`
4. JSON 파일 저장

다음 실행에서는 `PsdDecomposerApp.__init__`에서 `AppSettings.load`를 호출해 복원한다.

## 5. 처리 계층

내보내기는 GUI가 멈추지 않도록 워커 스레드에서 수행된다.

### 비동기 처리 흐름

1. `PsdDecomposerApp._start_export`
2. progress bar 표시
3. `threading.Thread(target=self._run_export, args=(job,), daemon=True).start()`
4. `root.after(100, self._poll_worker_queue)`
5. 워커 스레드에서 `PsdDecomposerApp._run_export`
6. `Exporter(progress=progress).export(job)`
7. 진행 메시지를 `worker_queue`에 추가
8. 메인 스레드에서 `PsdDecomposerApp._poll_worker_queue`
9. progress bar, 상태 문구, 완료/오류 messagebox 갱신

Tkinter 위젯은 메인 스레드에서만 안전하게 갱신할 수 있으므로, 워커 스레드는 직접 GUI를 만지지 않고 queue에 메시지만 넣는다.

### Exporter 공통 흐름

핵심 클래스는 `psd_decomposer.exporter.Exporter`다.

1. `Exporter.__init__`
2. `Exporter.export(job)`
3. 선택 레이어가 없으면 `PsdBackendError`
4. `PsdDocument(job.source_path)`로 PSD 다시 로드
5. `build_output_directory(job)`
6. 출력 폴더 생성
7. `job.export_format`에 따라 분기
   - `PNG`: `Exporter._export_png`
   - `PSD`: `Exporter._export_psd`

GUI에서 이미 PSD를 로드했더라도 Exporter는 워커 스레드에서 독립적으로 `PsdDocument`를 다시 생성한다. 이렇게 하면 GUI 미리보기 상태와 실제 저장 작업이 분리된다.

## 6. PNG 내보내기 상세 흐름

`Exporter._export_png`이 담당한다.

흐름:

1. `scale = job.rescale / 100`
2. `reserved_paths = set()`
3. `job.selected_layer_ids` 순회
4. `document.get_layer_info(layer_id)`
5. progress callback 호출
6. `Exporter._prepare_png_image(document, layer_id, job.preserve_canvas)`
7. `rescale`이 100%가 아니면 `Image.resize`
8. `build_base_name(job, layer)`
9. `resolve_output_path(...)`
10. `image.save(output_path)`
11. `outputs.append(output_path)`

### 캔버스 보존 또는 crop

`Exporter._prepare_png_image`가 `preserve_canvas`를 처리한다.

`preserve_canvas=False`:

- `document.render_layer(layer_id).convert("RGBA")` 결과를 그대로 반환한다.
- 결과 이미지는 레이어 오브젝트 영역만 가진다.

`preserve_canvas=True`:

- 원본 PSD 캔버스 크기의 투명 이미지 생성
- `LayerInfo.left`, `LayerInfo.top` 위치에 레이어 이미지를 `alpha_composite`
- 레이어가 캔버스 밖으로 나간 경우 source/destination 범위를 잘라 안전하게 합성
- 결과 이미지는 원본 PSD와 같은 크기를 가진다.

## 7. PSD 내보내기 상세 흐름

`Exporter._export_psd`가 담당한다.

PSD 출력은 Photoshop 자동화 없이 `psd_decomposer.psd_writer.write_layers_to_psd`로 새 PSD 파일을 생성한다. 모든 레이어는 `DocumentBackend.render_layer` 결과를 바탕으로 레스터화된 픽셀 레이어가 되며, 텍스트, 벡터, 스마트 오브젝트, 레이어 스타일 같은 Photoshop 객체 의미는 보존되지 않는다.

PSD 내보내기 흐름:

1. `reserved_paths = set()`
2. 선택 레이어 순회
3. `document.get_layer_info(layer_id)`
4. `build_base_name(job, layer)`
5. `resolve_output_path(..., "psd", ...)`
6. progress callback 호출
7. `write_layers_to_psd(document, (layer_id,), output_path, ...)`
8. `psd_tools.PSDImage.new`
9. `PSDImage.create_pixel_layer`
10. `PSDImage.save`
11. `outputs.append(output_path)`

재구성 모드에서는 `Exporter._export_reconstructed_document_psd`가 선택 레이어 전체를 하나의 새 PSD에 넣는다. GUI는 PSD 원본을 PSD로 내보내기 시작할 때 `messagebox.showwarning`으로 레스터화 경고를 표시한다.

## 8. 파일명과 출력 경로 흐름

파일명 관련 로직은 `psd_decomposer.naming`에 있다.

### 출력 폴더

`build_output_directory(job)`:

- `job.wrap_with_folder=False`: `job.output_directory`
- `job.wrap_with_folder=True`: `job.output_directory / "{원본파일명}_decomposed"`

### 기본 파일명

`build_base_name(job, layer, today=None)`:

1. `include_original_name=True`이면 원본 파일 stem 추가
2. `include_layer_name=True`이면 레이어명 추가
3. `include_date=True`이면 `YYMMDD` 추가
4. 아무 옵션도 선택되지 않았으면 레이어명을 fallback으로 사용
5. 각 조각을 `sanitize_filename_part`로 정리
6. `_`로 연결

### 파일명 정리

`sanitize_filename_part(value)`:

- Windows 파일명 금지 문자 제거
- 제어 문자 제거
- 연속 공백 정리
- 비어 있으면 `"layer"` 반환

### 충돌 해결

현재 Exporter는 `resolve_output_path`를 사용한다.

`resolve_output_path(directory, base_name, extension, overwrite_existing, reserved_paths)`:

- `overwrite_existing=True`이면 기존 파일은 덮어쓸 수 있다.
- 단, `reserved_paths`에 있는 경로는 같은 배치에서 이미 사용된 출력물이므로 덮어쓰지 않는다.
- 충돌하면 `_2`, `_3` 같은 suffix를 붙여 다음 후보를 찾는다.

이 로직 때문에 "기존 출력물 삭제"가 켜져 있어도, 같은 원본에서 같은 이름이 여러 번 생성될 때 방금 만든 파일을 자기 자신이 덮어쓰는 문제를 피한다.

`unique_output_path`는 기존 파일과 충돌하지 않는 경로를 찾는 보조 함수이며, 현재 Exporter 경로에서는 덮어쓰기 옵션까지 반영하는 `resolve_output_path`가 사용된다.

## 9. 오류와 상태 표시 흐름

공통 오류 타입은 `PsdBackendError`다.

사용 위치:

- `validate_input_path`
- `PsdDocument.__init__`
- `PsdDocument.get_layer_node`
- `PsdDocument.get_layer_info`
- `PsdDocument.render_layer`
- `PsdDocument.render_preview`
- `Exporter.export`
- `Exporter._export_psd`

GUI 오류 처리:

- 파일 로드 오류: `PsdDecomposerApp._load_file`에서 `messagebox.showerror`
- 내보내기 오류: `PsdDecomposerApp._poll_worker_queue`에서 `messagebox.showerror`
- PSD 원본을 PSD로 출력할 때 레스터화 경고: `PsdDecomposerApp._start_export`에서 `messagebox.showwarning`

상태 표시:

- 파일 처리 중: `PsdDecomposerApp._show_file_processing_message`
- 내보내기 진행 중: `PsdDecomposerApp._run_export`의 progress callback
- 완료: `_poll_worker_queue`의 `"done"` 분기
- 실패: `_poll_worker_queue`의 `"error"` 분기

## 10. 전체 데이터 흐름 요약

아래는 사용자가 PSD를 넣고 레이어를 내보낼 때의 전체 흐름이다.

```text
사용자 입력
  -> PsdDecomposerApp._browse_file 또는 _handle_drop
  -> PsdDecomposerApp._load_file
  -> PsdDocument.__init__
  -> validate_input_path
  -> PSDImage.open
  -> PsdDocument._collect_layers
  -> tuple[LayerInfo]
  -> PsdDecomposerApp._update_drop_zone
  -> PsdDecomposerApp._populate_layers
  -> 사용자가 레이어/출력 옵션 선택
  -> PsdDecomposerApp._start_export
  -> PsdDecomposerApp._current_selected_layer_ids
  -> PsdDecomposerApp._create_export_job
  -> ExportJob
  -> PsdDecomposerApp._run_export
  -> Exporter.export
  -> PsdDocument.__init__
  -> build_output_directory
  -> PNG이면 Exporter._export_png
       -> PsdDocument.render_layer
       -> Exporter._prepare_png_image
       -> build_base_name
       -> resolve_output_path
       -> Image.save
  -> PSD이면 Exporter._export_psd
       -> build_base_name
       -> resolve_output_path
       -> write_layers_to_psd
       -> PSDImage.create_pixel_layer
       -> PSDImage.save
  -> worker_queue
  -> PsdDecomposerApp._poll_worker_queue
  -> GUI 상태/진행률/완료 메시지 갱신
```

## 11. 계층별 책임 정리

### GUI 계층

대표 클래스:

- `PsdDecomposerApp`
- `Tooltip`

책임:

- 사용자 입력 받기
- 파일/출력 옵션 상태 보관
- 레이어 테이블 표시
- progress bar와 상태 메시지 표시
- Exporter를 백그라운드 스레드로 실행

### PSD 백엔드 계층

대표 클래스/함수:

- `PsdDocument`
- `PsdBackendError`
- `validate_input_path`

책임:

- PSD 파일 검증
- PSD 로드
- 레이어 메타데이터 수집
- 전체 미리보기 렌더링
- 개별 레이어 렌더링

### 데이터 모델 계층

대표 클래스:

- `LayerInfo`
- `ExportJob`

책임:

- GUI, 백엔드, Exporter 사이에서 주고받는 데이터를 명확한 구조로 고정

### 설정 계층

대표 클래스:

- `AppSettings`

책임:

- 사용자가 마지막으로 지정한 출력 옵션 저장
- 다음 실행 시 설정 복원

### 파일명/경로 계층

대표 함수:

- `sanitize_filename_part`
- `build_output_directory`
- `build_base_name`
- `unique_output_path`
- `resolve_output_path`

책임:

- 출력 폴더 결정
- 파일명 조합
- 파일명 안전화
- 파일 충돌 및 덮어쓰기 처리

### 내보내기 계층

대표 클래스:

- `Exporter`

책임:

- `ExportJob` 실행
- PNG 저장
- PSD 저장
- 진행 상황 callback 호출
- 생성된 출력 파일 경로 반환

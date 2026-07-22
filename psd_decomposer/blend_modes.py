from __future__ import annotations

from enum import Enum

from PIL import Image


class LayerBlendMode(str, Enum):
    """PSD와 Aseprite가 공유하거나 변환할 수 있는 레이어 블렌드 모드입니다."""

    PASS_THROUGH = "pass_through"
    NORMAL = "normal"
    DISSOLVE = "dissolve"
    DARKEN = "darken"
    MULTIPLY = "multiply"
    COLOR_BURN = "color_burn"
    LINEAR_BURN = "linear_burn"
    DARKER_COLOR = "darker_color"
    LIGHTEN = "lighten"
    SCREEN = "screen"
    COLOR_DODGE = "color_dodge"
    ADDITION = "addition"
    LIGHTER_COLOR = "lighter_color"
    OVERLAY = "overlay"
    SOFT_LIGHT = "soft_light"
    HARD_LIGHT = "hard_light"
    VIVID_LIGHT = "vivid_light"
    LINEAR_LIGHT = "linear_light"
    PIN_LIGHT = "pin_light"
    HARD_MIX = "hard_mix"
    DIFFERENCE = "difference"
    EXCLUSION = "exclusion"
    SUBTRACT = "subtract"
    DIVIDE = "divide"
    HUE = "hue"
    SATURATION = "saturation"
    COLOR = "color"
    LUMINOSITY = "luminosity"
    UNKNOWN = "unknown"


ASEPRITE_BLEND_MODE_BY_VALUE = {
    0: LayerBlendMode.NORMAL,
    1: LayerBlendMode.MULTIPLY,
    2: LayerBlendMode.SCREEN,
    3: LayerBlendMode.OVERLAY,
    4: LayerBlendMode.DARKEN,
    5: LayerBlendMode.LIGHTEN,
    6: LayerBlendMode.COLOR_DODGE,
    7: LayerBlendMode.COLOR_BURN,
    8: LayerBlendMode.HARD_LIGHT,
    9: LayerBlendMode.SOFT_LIGHT,
    10: LayerBlendMode.DIFFERENCE,
    11: LayerBlendMode.EXCLUSION,
    12: LayerBlendMode.HUE,
    13: LayerBlendMode.SATURATION,
    14: LayerBlendMode.COLOR,
    15: LayerBlendMode.LUMINOSITY,
    16: LayerBlendMode.ADDITION,
    17: LayerBlendMode.SUBTRACT,
    18: LayerBlendMode.DIVIDE,
}
ASEPRITE_VALUE_BY_BLEND_MODE = {mode: value for value, mode in ASEPRITE_BLEND_MODE_BY_VALUE.items()}

PSD_BLEND_MODE_BY_VALUE = {
    b"pass": LayerBlendMode.PASS_THROUGH,
    b"norm": LayerBlendMode.NORMAL,
    b"diss": LayerBlendMode.DISSOLVE,
    b"dark": LayerBlendMode.DARKEN,
    b"mul ": LayerBlendMode.MULTIPLY,
    b"idiv": LayerBlendMode.COLOR_BURN,
    b"lbrn": LayerBlendMode.LINEAR_BURN,
    b"dkCl": LayerBlendMode.DARKER_COLOR,
    b"lite": LayerBlendMode.LIGHTEN,
    b"scrn": LayerBlendMode.SCREEN,
    b"div ": LayerBlendMode.COLOR_DODGE,
    b"lddg": LayerBlendMode.ADDITION,
    b"lgCl": LayerBlendMode.LIGHTER_COLOR,
    b"over": LayerBlendMode.OVERLAY,
    b"sLit": LayerBlendMode.SOFT_LIGHT,
    b"hLit": LayerBlendMode.HARD_LIGHT,
    b"vLit": LayerBlendMode.VIVID_LIGHT,
    b"lLit": LayerBlendMode.LINEAR_LIGHT,
    b"pLit": LayerBlendMode.PIN_LIGHT,
    b"hMix": LayerBlendMode.HARD_MIX,
    b"diff": LayerBlendMode.DIFFERENCE,
    b"smud": LayerBlendMode.EXCLUSION,
    b"fsub": LayerBlendMode.SUBTRACT,
    b"fdiv": LayerBlendMode.DIVIDE,
    b"hue ": LayerBlendMode.HUE,
    b"sat ": LayerBlendMode.SATURATION,
    b"colr": LayerBlendMode.COLOR,
    b"lum ": LayerBlendMode.LUMINOSITY,
}
PSD_VALUE_BY_BLEND_MODE = {mode: value for value, mode in PSD_BLEND_MODE_BY_VALUE.items()}

BLEND_MODE_DISPLAY_NAMES = {
    LayerBlendMode.PASS_THROUGH: "통과",
    LayerBlendMode.NORMAL: "표준",
    LayerBlendMode.DISSOLVE: "디졸브",
    LayerBlendMode.DARKEN: "어둡게 하기",
    LayerBlendMode.MULTIPLY: "곱하기",
    LayerBlendMode.COLOR_BURN: "색상 번",
    LayerBlendMode.LINEAR_BURN: "선형 번",
    LayerBlendMode.DARKER_COLOR: "어두운 색상",
    LayerBlendMode.LIGHTEN: "밝게 하기",
    LayerBlendMode.SCREEN: "스크린",
    LayerBlendMode.COLOR_DODGE: "색상 닷지",
    LayerBlendMode.ADDITION: "더하기",
    LayerBlendMode.LIGHTER_COLOR: "밝은 색상",
    LayerBlendMode.OVERLAY: "오버레이",
    LayerBlendMode.SOFT_LIGHT: "소프트 라이트",
    LayerBlendMode.HARD_LIGHT: "하드 라이트",
    LayerBlendMode.VIVID_LIGHT: "선명한 라이트",
    LayerBlendMode.LINEAR_LIGHT: "선형 라이트",
    LayerBlendMode.PIN_LIGHT: "핀 라이트",
    LayerBlendMode.HARD_MIX: "하드 혼합",
    LayerBlendMode.DIFFERENCE: "차이",
    LayerBlendMode.EXCLUSION: "제외",
    LayerBlendMode.SUBTRACT: "빼기",
    LayerBlendMode.DIVIDE: "나누기",
    LayerBlendMode.HUE: "색조",
    LayerBlendMode.SATURATION: "채도",
    LayerBlendMode.COLOR: "색상",
    LayerBlendMode.LUMINOSITY: "광도",
    LayerBlendMode.UNKNOWN: "알 수 없음",
}


def blend_mode_from_aseprite(value: int) -> LayerBlendMode:
    """Aseprite Layer Chunk의 숫자 값을 공통 블렌드 모드로 변환합니다."""

    return ASEPRITE_BLEND_MODE_BY_VALUE.get(value, LayerBlendMode.UNKNOWN)


def blend_mode_to_aseprite(mode: LayerBlendMode) -> int | None:
    """공통 블렌드 모드를 Aseprite Layer Chunk 숫자 값으로 변환합니다."""

    return ASEPRITE_VALUE_BY_BLEND_MODE.get(mode)


def blend_mode_from_psd(value: object) -> LayerBlendMode:
    """psd-tools의 BlendMode 값 또는 PSD 4바이트 키를 공통 블렌드 모드로 변환합니다."""

    # psd-tools Enum은 실제 PSD 키를 value 속성에 보관하므로 외부 타입에 결합하지 않고 bytes만 꺼냅니다.
    raw_value = getattr(value, "value", value)
    if isinstance(raw_value, str):
        raw_value = raw_value.encode("ascii", errors="replace")
    return PSD_BLEND_MODE_BY_VALUE.get(raw_value, LayerBlendMode.UNKNOWN)


def blend_mode_to_psd(mode: LayerBlendMode) -> bytes | None:
    """공통 블렌드 모드를 PSD 레이어 레코드의 4바이트 키로 변환합니다."""

    return PSD_VALUE_BY_BLEND_MODE.get(mode)


def blend_mode_display_name(mode: LayerBlendMode) -> str:
    """GUI 경고에 사용할 한글 블렌드 모드 이름을 반환합니다."""

    return BLEND_MODE_DISPLAY_NAMES[mode]


def composite_layer(
    backdrop: Image.Image,
    source: Image.Image,
    dest: tuple[int, int],
    blend_mode: LayerBlendMode,
) -> Image.Image:
    """원본 위치와 블렌드 모드를 적용해 RGBA 레이어를 캔버스 위에 합성합니다."""

    canvas = backdrop.convert("RGBA")
    layer = source.convert("RGBA")
    left, top = dest

    # 캔버스 밖으로 벗어난 레이어는 실제로 겹치는 영역만 잘라 NumPy 연산 크기를 제한합니다.
    source_left = max(0, -left)
    source_top = max(0, -top)
    dest_left = max(0, left)
    dest_top = max(0, top)
    width = min(layer.width - source_left, canvas.width - dest_left)
    height = min(layer.height - source_top, canvas.height - dest_top)
    if width <= 0 or height <= 0:
        return canvas

    source_region = layer.crop((source_left, source_top, source_left + width, source_top + height))
    backdrop_region = canvas.crop((dest_left, dest_top, dest_left + width, dest_top + height))
    blended_region = _blend_rgba_regions(backdrop_region, source_region, blend_mode)
    canvas.paste(blended_region, (dest_left, dest_top))
    return canvas


def normal_equivalent_layer(
    backdrop: Image.Image,
    source: Image.Image,
    dest: tuple[int, int],
    blend_mode: LayerBlendMode,
) -> Image.Image:
    """같은 배경 위에 Normal로 올렸을 때 원본 블렌드 결과와 같은 RGBA 레이어를 만듭니다."""

    layer = source.convert("RGBA")
    if blend_mode in {LayerBlendMode.NORMAL, LayerBlendMode.PASS_THROUGH, LayerBlendMode.UNKNOWN}:
        return layer

    canvas = backdrop.convert("RGBA")
    left, top = dest

    # 캔버스와 겹치지 않는 픽셀은 투명 배경 위에 놓인 것과 같으므로 원본 색을 유지합니다.
    source_left = max(0, -left)
    source_top = max(0, -top)
    dest_left = max(0, left)
    dest_top = max(0, top)
    width = min(layer.width - source_left, canvas.width - dest_left)
    height = min(layer.height - source_top, canvas.height - dest_top)
    if width <= 0 or height <= 0:
        return layer

    # 현재 레이어의 알파는 보존하고, 배경 알파와 블렌드 색을 반영한 등가 RGB만 계산합니다.
    source_region = layer.crop((source_left, source_top, source_left + width, source_top + height))
    backdrop_region = canvas.crop((dest_left, dest_top, dest_left + width, dest_top + height))
    equivalent_region = _normal_equivalent_rgba_region(backdrop_region, source_region, blend_mode)
    layer.paste(equivalent_region, (source_left, source_top))
    return layer


def _normal_equivalent_rgba_region(
    backdrop: Image.Image,
    source: Image.Image,
    blend_mode: LayerBlendMode,
) -> Image.Image:
    """같은 크기의 배경과 소스를 Normal 합성용 등가 RGBA 영역으로 변환합니다."""

    import numpy as np
    from psd_tools.composite.blend import BLEND_FUNC
    from psd_tools.constants import BlendMode as PsdBlendMode

    backdrop_array = np.asarray(backdrop, dtype=np.float32) / 255.0
    source_array = np.asarray(source, dtype=np.float32) / 255.0
    backdrop_color = backdrop_array[:, :, :3]
    source_color = source_array[:, :, :3]
    backdrop_alpha = backdrop_array[:, :, 3:4]

    # 특수 모드 색과 원본 색을 배경 알파로 보간하면 Normal source-over에서 같은 최종 색을 얻습니다.
    psd_value = blend_mode_to_psd(blend_mode) or blend_mode_to_psd(LayerBlendMode.NORMAL)
    assert psd_value is not None
    blend_function = BLEND_FUNC[PsdBlendMode(psd_value)]
    blended_color = np.clip(blend_function(backdrop_color, source_color), 0.0, 1.0)
    equivalent_color = (1.0 - backdrop_alpha) * source_color + backdrop_alpha * blended_color

    # 출력 알파는 원본 레이어와 같아야 배경 위에서 Normal 합성한 알파도 원본 결과와 일치합니다.
    output_array = np.concatenate((equivalent_color, source_array[:, :, 3:4]), axis=2)
    output_bytes = np.rint(np.clip(output_array, 0.0, 1.0) * 255.0).astype(np.uint8)
    return Image.fromarray(output_bytes, mode="RGBA")


def _blend_rgba_regions(
    backdrop: Image.Image,
    source: Image.Image,
    blend_mode: LayerBlendMode,
) -> Image.Image:
    """같은 크기의 RGBA 영역을 premultiplied alpha 합성 공식으로 계산합니다."""

    import numpy as np
    from psd_tools.composite.blend import BLEND_FUNC
    from psd_tools.constants import BlendMode as PsdBlendMode

    backdrop_array = np.asarray(backdrop, dtype=np.float32) / 255.0
    source_array = np.asarray(source, dtype=np.float32) / 255.0
    backdrop_color = backdrop_array[:, :, :3]
    source_color = source_array[:, :, :3]
    backdrop_alpha = backdrop_array[:, :, 3:4]
    source_alpha = source_array[:, :, 3:4]

    # 그룹 전용 통과 모드와 알 수 없는 모드는 시각화 경로에서만 표준 모드로 대체합니다.
    effective_mode = (
        LayerBlendMode.NORMAL
        if blend_mode in {LayerBlendMode.PASS_THROUGH, LayerBlendMode.UNKNOWN}
        else blend_mode
    )
    psd_value = blend_mode_to_psd(effective_mode) or blend_mode_to_psd(LayerBlendMode.NORMAL)
    assert psd_value is not None
    blend_function = BLEND_FUNC[PsdBlendMode(psd_value)]
    blended_color = np.clip(blend_function(backdrop_color, source_color), 0.0, 1.0)

    # PDF/Photoshop 계열 source-over 블렌드 공식을 사용해 반투명 픽셀의 색과 알파를 함께 계산합니다.
    output_alpha = source_alpha + backdrop_alpha * (1.0 - source_alpha)
    premultiplied_color = source_alpha * (
        (1.0 - backdrop_alpha) * source_color + backdrop_alpha * blended_color
    ) + backdrop_alpha * (1.0 - source_alpha) * backdrop_color
    output_color = np.divide(
        premultiplied_color,
        output_alpha,
        out=np.zeros_like(premultiplied_color),
        where=output_alpha > 0,
    )
    output_array = np.concatenate((output_color, output_alpha), axis=2)
    output_bytes = np.rint(np.clip(output_array, 0.0, 1.0) * 255.0).astype(np.uint8)
    return Image.fromarray(output_bytes, mode="RGBA")

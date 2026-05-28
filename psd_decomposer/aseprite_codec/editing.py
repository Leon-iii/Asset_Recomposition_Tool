from __future__ import annotations

from dataclasses import replace
from typing import Callable

from .errors import AseEditError
from .model import AseFrame, AsepriteFile, CelChunk, LayerChunk


VISIBLE_LAYER_FLAG = 1


def rename_layer(ase_file: AsepriteFile, layer_index: int, new_name: str) -> AsepriteFile:
    """레이어 index로 대상 레이어를 찾아 이름을 바꾼 새 AsepriteFile을 반환합니다."""

    if not new_name:
        raise AseEditError("레이어 이름은 비워 둘 수 없습니다.")
    return _replace_layer(ase_file, layer_index, lambda layer: replace(layer, name=new_name, dirty=True))


def rename_layer_by_name(ase_file: AsepriteFile, current_name: str, new_name: str) -> AsepriteFile:
    """유일한 레이어 이름으로 대상 레이어를 찾아 이름을 바꾼 새 AsepriteFile을 반환합니다."""

    return rename_layer(ase_file, _unique_layer_index_by_name(ase_file, current_name), new_name)


def set_layer_visibility(ase_file: AsepriteFile, layer_index: int, visible: bool) -> AsepriteFile:
    """레이어 index로 대상 레이어를 찾아 표시 상태를 바꾼 새 AsepriteFile을 반환합니다."""

    def edit(layer: LayerChunk) -> LayerChunk:
        flags = layer.flags | VISIBLE_LAYER_FLAG if visible else layer.flags & ~VISIBLE_LAYER_FLAG
        return replace(layer, flags=flags, visible=visible, dirty=True)

    return _replace_layer(ase_file, layer_index, edit)


def set_layer_visibility_by_name(ase_file: AsepriteFile, layer_name: str, visible: bool) -> AsepriteFile:
    """유일한 레이어 이름으로 대상 레이어를 찾아 표시 상태를 바꾼 새 AsepriteFile을 반환합니다."""

    return set_layer_visibility(ase_file, _unique_layer_index_by_name(ase_file, layer_name), visible)


def set_only_layers_visible(ase_file: AsepriteFile, visible_layer_indices: set[int]) -> AsepriteFile:
    """선택한 레이어만 visible=true로 두고 나머지 레이어는 visible=false로 바꿉니다."""

    edited = ase_file
    for layer in ase_file.layers:
        edited = set_layer_visibility(edited, layer.index, layer.index in visible_layer_indices)
    return edited


def keep_layers(ase_file: AsepriteFile, layer_indices: set[int]) -> AsepriteFile:
    """선택한 레이어와 그 레이어의 Cel만 남긴 새 AsepriteFile을 반환합니다."""

    if not layer_indices:
        raise AseEditError("남길 레이어가 하나 이상 필요합니다.")

    missing = sorted(layer_indices - {layer.index for layer in ase_file.layers})
    if missing:
        raise AseEditError(f"레이어 index를 찾을 수 없습니다: {missing[0]}")

    index_map: dict[int, int] = {}
    layers: list[LayerChunk] = []
    for new_index, layer in enumerate(layer for layer in ase_file.layers if layer.index in layer_indices):
        index_map[layer.index] = new_index
        layers.append(replace(layer, index=new_index, dirty=True))

    frames = [_keep_layers_in_frame(frame, index_map) for frame in ase_file.frames]
    return replace(ase_file, frames=frames, layers=layers)


def _replace_layer(ase_file: AsepriteFile, layer_index: int, edit: Callable[[LayerChunk], LayerChunk]) -> AsepriteFile:
    layer = _layer_by_index(ase_file, layer_index)
    edited_layer = edit(layer)

    frames = [_replace_layer_in_frame(frame, layer_index, edited_layer) for frame in ase_file.frames]
    layers = [edited_layer if layer.index == layer_index else layer for layer in ase_file.layers]
    return replace(ase_file, frames=frames, layers=layers)


def _replace_layer_in_frame(frame: AseFrame, layer_index: int, edited_layer: LayerChunk) -> AseFrame:
    chunks = [edited_layer if isinstance(chunk, LayerChunk) and chunk.index == layer_index else chunk for chunk in frame.chunks]
    return replace(frame, chunks=chunks)


def _keep_layers_in_frame(frame: AseFrame, index_map: dict[int, int]) -> AseFrame:
    chunks: list[object] = []
    for chunk in frame.chunks:
        if isinstance(chunk, LayerChunk):
            if chunk.index in index_map:
                chunks.append(replace(chunk, index=index_map[chunk.index], dirty=True))
            continue
        if isinstance(chunk, CelChunk):
            if chunk.layer_index in index_map:
                new_layer_index = index_map[chunk.layer_index]
                chunks.append(replace(chunk, layer_index=new_layer_index, dirty=chunk.dirty or new_layer_index != chunk.layer_index))
            continue
        chunks.append(chunk)
    return replace(frame, chunks=chunks)


def _layer_by_index(ase_file: AsepriteFile, layer_index: int) -> LayerChunk:
    for layer in ase_file.layers:
        if layer.index == layer_index:
            return layer
    raise AseEditError(f"레이어 index를 찾을 수 없습니다: {layer_index}")


def _unique_layer_index_by_name(ase_file: AsepriteFile, layer_name: str) -> int:
    matches = [layer.index for layer in ase_file.layers if layer.name == layer_name]
    if not matches:
        raise AseEditError(f"레이어 이름을 찾을 수 없습니다: {layer_name}")
    if len(matches) > 1:
        raise AseEditError(f"동일한 이름의 레이어가 여러 개입니다: {layer_name}")
    return matches[0]

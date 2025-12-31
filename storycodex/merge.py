from __future__ import annotations

from typing import Any


JsonValue = Any


def merge(base: JsonValue, override: JsonValue) -> JsonValue:
    if isinstance(base, dict) and isinstance(override, dict):
        return merge_dicts(base, override)
    if isinstance(base, list) and isinstance(override, list):
        return merge_lists(base, override)
    return override


def merge_dicts(base: dict[str, JsonValue], override: dict[str, JsonValue]) -> dict[str, JsonValue]:
    merged: dict[str, JsonValue] = {}
    for key in base.keys() | override.keys():
        if key in base and key in override:
            merged[key] = merge(base[key], override[key])
        elif key in base:
            merged[key] = base[key]
        else:
            merged[key] = override[key]
    return merged


def merge_lists(base: list[JsonValue], override: list[JsonValue]) -> list[JsonValue]:
    result: list[JsonValue] = []
    for item in base + override:
        if not any(item == existing for existing in result):
            result.append(item)
    return result

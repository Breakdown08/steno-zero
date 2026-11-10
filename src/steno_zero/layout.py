"""Keyboard layout as data: which KeyboardEvent.code each finger presses."""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from steno_zero.chords import FINGERS, N_KEYS

LAYOUT_FORMAT: str = "steno-zero/layout"
LAYOUT_VERSION: int = 1
LAYOUTS_DIR: Path = Path("data/layouts")
CODE_PATTERN: str = "[A-Za-z0-9]+"
NAME_PATTERN: str = "[a-z0-9-]+"
RESERVED_CODES: tuple[str, ...] = ("Slash", "Escape")  # help key and skip key of the page


class LayoutError(ValueError): ...


@dataclass(frozen=True)
class Layout:
    name: str
    codes: tuple[str, ...]
    labels: tuple[str, ...]


def layout_obj(layout: Layout) -> dict[str, Any]:
    return {
        "name": layout.name,
        "keys": [
            {"finger": FINGERS[i], "code": layout.codes[i], "label": layout.labels[i]} for i in range(N_KEYS)
        ],
    }


def layout_from_obj(obj: object) -> Layout:
    if not isinstance(obj, dict):
        raise LayoutError("layout must be an object")
    name: Any = obj.get("name")
    if not isinstance(name, str) or re.fullmatch(NAME_PATTERN, name) is None:
        raise LayoutError(f"layout name must match {NAME_PATTERN}")
    keys: Any = obj.get("keys")
    if not isinstance(keys, list) or len(keys) != N_KEYS:
        raise LayoutError(f"keys must be a list of {N_KEYS} objects")
    codes: list[str] = []
    labels: list[str] = []
    i: int
    key: Any
    for i, key in enumerate(keys):
        if not isinstance(key, dict):
            raise LayoutError(f"key {i} must be an object")
        if key.get("finger") != FINGERS[i]:
            raise LayoutError(f"key {i} must be the finger {FINGERS[i]}")
        code: Any = key.get("code")
        if not isinstance(code, str) or re.fullmatch(CODE_PATTERN, code) is None:
            raise LayoutError(f"code of {FINGERS[i]} must match {CODE_PATTERN}")
        if code in codes:
            raise LayoutError(f"code {code} is used twice")
        if code in RESERVED_CODES:
            raise LayoutError(f"code {code} is reserved for the page")
        label: Any = key.get("label")
        if not isinstance(label, str) or label == "":
            raise LayoutError(f"label of {FINGERS[i]} must be a non-empty string")
        codes.append(code)
        labels.append(label)
    return Layout(name, tuple(codes), tuple(labels))


def layout_json(layout: Layout) -> str:
    obj: dict[str, Any] = {"format": LAYOUT_FORMAT, "version": LAYOUT_VERSION, **layout_obj(layout)}
    return json.dumps(obj, ensure_ascii=False, indent=1) + "\n"


def read_layout(text: str) -> Layout:
    try:
        obj: Any = json.loads(text)
    except ValueError as exc:
        raise LayoutError(f"bad JSON: {exc}") from exc
    if not isinstance(obj, dict):
        raise LayoutError("layout file must be an object")
    version: Any = obj.get("version")
    if obj.get("format") != LAYOUT_FORMAT or isinstance(version, bool) or version != LAYOUT_VERSION:
        raise LayoutError(f"not a {LAYOUT_FORMAT} file, version {LAYOUT_VERSION}")
    return layout_from_obj(obj)


def read_layouts(folder: Path) -> tuple[Layout, ...]:
    layouts: list[Layout] = []
    path: Path
    for path in sorted(folder.glob("*.json")):
        try:
            layouts.append(read_layout(path.read_text(encoding="utf-8")))
        except LayoutError as exc:
            raise LayoutError(f"{path}: {exc}") from exc
    names: list[str] = [x.name for x in layouts]
    if len(set(names)) != len(names):
        raise LayoutError(f"layout names repeat in {folder}")
    return tuple(sorted(layouts, key=lambda x: x.name))

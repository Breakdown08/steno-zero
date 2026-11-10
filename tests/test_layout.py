"""Checks 4-7: the layout file, its reading and writing."""

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from steno_zero.layout import (
    Layout,
    LayoutError,
    layout_from_obj,
    layout_json,
    layout_obj,
    read_layout,
    read_layouts,
)
from tests.helpers import ROOT
from tests.layout_helpers import SPACE, VM, VM_CODES, VM_LABELS, ZZ, layout_dict, layout_obj_of, layout_text

LAYOUT_FILE: Path = ROOT / "data" / "layouts" / "qwerty-vm.json"


def test_committed_layout() -> None:
    text: str = LAYOUT_FILE.read_text(encoding="utf-8")
    layout: Layout = read_layout(text)
    assert layout.name == "qwerty-vm"
    assert layout.codes == (
        "KeyA",
        "KeyS",
        "KeyD",
        "KeyF",
        "KeyV",
        "KeyM",
        "KeyJ",
        "KeyK",
        "KeyL",
        "Semicolon",
    )
    assert layout.labels == ("a", "s", "d", "f", "v", "m", "j", "k", "l", ";")
    assert layout_json(layout) == text


@pytest.mark.parametrize("layout", [VM, SPACE, ZZ], ids=lambda x: x.name)
def test_layout_json_round_trip(layout: Layout) -> None:
    assert read_layout(layout_json(layout)) == layout


def test_layout_json_text_and_obj() -> None:
    assert layout_obj(VM) == layout_obj_of(VM)
    assert layout_json(VM) == layout_text(VM)
    assert layout_json(VM).endswith("}\n")
    assert layout_from_obj(layout_obj_of(SPACE)) == SPACE


def edited(**changes: object) -> str:
    obj: dict[str, Any] = layout_dict()
    obj.update(changes)
    return json.dumps(obj)


def with_key(index: int, **changes: object) -> str:
    obj: dict[str, Any] = copy.deepcopy(layout_dict())
    obj["keys"][index].update(changes)
    return json.dumps(obj)


def with_keys(keys: list[dict[str, Any]]) -> str:
    return edited(keys=keys)


def key_items() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = layout_dict()["keys"]
    return items


BAD: dict[str, str] = {
    "foreign format": edited(format="steno-zero/keyboard-profile"),
    "version 2": edited(version=2),
    "nine keys": with_keys(key_items()[:9]),
    "eleven keys": with_keys([*key_items(), {"finger": "R4", "code": "KeyP", "label": "p"}]),
    "keys not a list": edited(keys={}),
    "finger out of place": with_key(3, finger="L0"),
    "code repeated": with_key(1, code="KeyA"),
    "code Slash": with_key(0, code="Slash"),
    "code Escape": with_key(0, code="Escape"),
    "code with a space": with_key(0, code="Key A"),
    "empty label": with_key(0, label=""),
    "label not a string": with_key(0, label=1),
    "name uppercase": edited(name="Qwerty"),
    "not an object": "[]",
    "not json": "{",
}


@pytest.mark.parametrize("name", sorted(BAD))
def test_read_layout_rejects(name: str) -> None:
    with pytest.raises(LayoutError):
        read_layout(BAD[name])


def test_layout_error_is_value_error() -> None:
    assert issubclass(LayoutError, ValueError)


def test_layout_from_obj_rejects_a_non_object() -> None:
    with pytest.raises(LayoutError):
        layout_from_obj([])


def test_read_layouts_sorted_by_name(tmp_path: Path) -> None:
    (tmp_path / "b.json").write_text(layout_text(ZZ), encoding="utf-8")
    (tmp_path / "a.json").write_text(layout_text(VM), encoding="utf-8")
    assert read_layouts(tmp_path) == (VM, ZZ)


def test_read_layouts_repeated_name(tmp_path: Path) -> None:
    (tmp_path / "one.json").write_text(layout_text(VM), encoding="utf-8")
    (tmp_path / "two.json").write_text(
        layout_text(Layout("qwerty-vm", ZZ.codes, ZZ.labels)), encoding="utf-8"
    )
    with pytest.raises(LayoutError):
        read_layouts(tmp_path)


def test_helpers_agree_with_the_spec() -> None:
    assert VM.codes == VM_CODES
    assert VM.labels == VM_LABELS

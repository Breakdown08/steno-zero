"""Layouts shared by the tests, written out by hand so that they do not depend on the code under test."""

import json
from typing import Any

from steno_zero.layout import Layout

FINGER_NAMES: tuple[str, ...] = ("L4", "L3", "L2", "L1", "L0", "R0", "R1", "R2", "R3", "R4")
VM_CODES: tuple[str, ...] = (
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
VM_LABELS: tuple[str, ...] = ("a", "s", "d", "f", "v", "m", "j", "k", "l", ";")
# The layout of the first release: the right thumb on KeyN.
OLD_CODES: tuple[str, ...] = (
    "KeyA",
    "KeyS",
    "KeyD",
    "KeyF",
    "KeyV",
    "KeyN",
    "KeyJ",
    "KeyK",
    "KeyL",
    "Semicolon",
)
OLD_LABELS: tuple[str, ...] = ("a", "s", "d", "f", "v", "n", "j", "k", "l", ";")

VM: Layout = Layout("qwerty-vm", VM_CODES, VM_LABELS)
# L2 on KeyK and R2 on KeyD: the same ten keys, two fingers swapped.
SWAP_CODES: tuple[str, ...] = (
    "KeyA",
    "KeyS",
    "KeyK",
    "KeyF",
    "KeyV",
    "KeyM",
    "KeyJ",
    "KeyD",
    "KeyL",
    "Semicolon",
)
SWAPPED: Layout = Layout("qwerty-swap", SWAP_CODES, ("a", "s", "k", "f", "v", "m", "j", "d", "l", ";"))
# R2 on KeyL and R3 on KeyK.
KL_CODES: tuple[str, ...] = (
    "KeyA",
    "KeyS",
    "KeyD",
    "KeyF",
    "KeyV",
    "KeyM",
    "KeyJ",
    "KeyL",
    "KeyK",
    "Semicolon",
)
KL_SWAPPED: Layout = Layout("qwerty-kl", KL_CODES, ("a", "s", "d", "f", "v", "m", "j", "l", "k", ";"))
# L0 on Space: a layout with a code that qwerty-vm has not got.
SPACE_CODES: tuple[str, ...] = (
    "KeyA",
    "KeyS",
    "KeyD",
    "KeyF",
    "Space",
    "KeyM",
    "KeyJ",
    "KeyK",
    "KeyL",
    "Semicolon",
)
SPACE: Layout = Layout("space-thumb", SPACE_CODES, ("a", "s", "d", "f", "_", "m", "j", "k", "l", ";"))
# The old keys under another name: the layout that the migrated profile laptop-vn covers.
ZZ: Layout = Layout("zz", OLD_CODES, OLD_LABELS)


def layout_obj_of(layout: Layout) -> dict[str, Any]:
    return {
        "name": layout.name,
        "keys": [
            {"finger": FINGER_NAMES[i], "code": layout.codes[i], "label": layout.labels[i]} for i in range(10)
        ],
    }


def layout_dict(layout: Layout = VM) -> dict[str, Any]:
    return {"format": "steno-zero/layout", "version": 1, **layout_obj_of(layout)}


def layout_text(layout: Layout = VM) -> str:
    return json.dumps(layout_dict(layout), ensure_ascii=False, indent=1) + "\n"

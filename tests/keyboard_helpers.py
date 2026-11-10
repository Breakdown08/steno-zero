"""Builders of calibration logs and keyboard profiles shared by the keyboard, drill and price tests."""

import itertools
import json
from typing import Any

from steno_zero.keyboard import Blocked, KeyboardProfile
from steno_zero.layout import Layout
from tests.layout_helpers import OLD_CODES, VM, VM_CODES, layout_obj_of

STARTED: str = "2026-11-10T09:00:00.000Z"
CREATED: str = "2026-11-10T00:00:00.000Z"
VM_SORTED: tuple[str, ...] = tuple(sorted(VM_CODES))
# The profile of the check 13: KeyF, KeyV and KeyK together do not pass (finger chord 152 on qwerty-vm).
P1: KeyboardProfile = KeyboardProfile(
    "test", "c", CREATED, VM_SORTED, (Blocked(("KeyF", "KeyK", "KeyV"), False),)
)
# L4 L3 L2 (7) and R2 R3 R4 (896) on qwerty-vm.
P2: KeyboardProfile = KeyboardProfile(
    "test",
    "c",
    CREATED,
    VM_SORTED,
    (Blocked(("KeyA", "KeyD", "KeyS"), False), Blocked(("KeyK", "KeyL", "Semicolon"), False)),
)
# The migrated profile laptop-vn: the old keys (KeyN, no KeyM) and the eight blocks of the first calibration.
LAPTOP_VN: KeyboardProfile = KeyboardProfile(
    "laptop-vn",
    "calibration-2026-11-09T09-57-23.069Z",
    "2026-11-09T09:57:23.069Z",
    tuple(sorted(OLD_CODES)),
    tuple(
        Blocked(k, True)
        for k in (
            ("KeyA", "KeyD", "KeyJ"),
            ("KeyA", "KeyD", "KeyK"),
            ("KeyD", "KeyF", "KeyV"),
            ("KeyD", "KeyJ", "KeyV"),
            ("KeyD", "KeyN", "KeyV"),
            ("KeyF", "KeyK", "KeyV"),
            ("KeyF", "KeyL", "KeyV"),
            ("KeyF", "KeyV", "Semicolon"),
        )
    ),
)
P1_BLOCKED: tuple[int, ...] = (152,)
P2_BLOCKED: tuple[int, ...] = (7, 896)


def combos() -> list[int]:
    """The 45 pairs and 120 triples, each ascending, written independently of the code under test."""
    out: list[int] = []
    size: int
    for size in (2, 3):
        group: list[int] = sorted(sum(1 << k for k in ks) for ks in itertools.combinations(range(10), size))
        out += group
    return out


type Row = tuple[int, int]  # target, typed


def calibration_dict(
    overrides: dict[int, list[int]] | None = None,
    session: str = "calibration-2026-11-10T09-00-00.000Z",
    layout: Layout = VM,
) -> dict[str, Any]:
    """One correct attempt per combination, except the combinations in `overrides`: target -> typed list."""
    changes: dict[int, list[int]] = overrides if overrides is not None else {}
    rows: list[Row] = []
    c: int
    for c in combos():
        typed: int
        for typed in changes.get(c, [c]):
            rows.append((c, typed))
    return {
        "format": "steno-zero/keyboard-calibration",
        "version": 2,
        "session": session,
        "started": STARTED,
        "finished": "2026-11-10T09:06:00.000Z",
        "user_agent": "pytest",
        "max_held": 3,
        "layout": layout_obj_of(layout),
        "attempts": [
            {"target": t, "typed": ty, "down_ms": 100.0 * k, "up_ms": 100.0 * k + 50.5}
            for k, (t, ty) in enumerate(rows)
        ],
    }


def calibration_text(overrides: dict[int, list[int]] | None = None, layout: Layout = VM) -> str:
    return json.dumps(calibration_dict(overrides, layout=layout))


# The log of check 8: 152 never gets through (a key is lost), 7 gets 3, 3, 15, 24 fails once and then passes.
CHECK5: dict[int, list[int]] = {152: [24, 24, 24], 7: [3, 3, 15], 24: [8, 24]}
# The same physical failures when L2 and R2 are swapped (bits 2 and 7 exchanged in target and typed).
CHECK5_SWAPPED: dict[int, list[int]] = {28: [24, 24, 24], 131: [3, 3, 139], 24: [8, 24]}
# What the log CHECK5 gives, in codes.
CHECK5_BLOCKED: tuple[Blocked, ...] = (
    Blocked(("KeyA", "KeyD", "KeyS"), True),
    Blocked(("KeyF", "KeyK", "KeyV"), False),
)


def profile_dict(
    blocked: list[tuple[tuple[str, ...], bool]],
    name: str = "test",
    keys: tuple[str, ...] = VM_SORTED,
) -> dict[str, Any]:
    return {
        "format": "steno-zero/keyboard-profile",
        "version": 2,
        "name": name,
        "session": "calibration-2026-11-10T09-00-00.000Z",
        "created": STARTED,
        "keys": list(keys),
        "blocked": [{"keys": list(k), "unclear": u} for k, u in blocked],
    }


def count_available(max_keys: int, blocked: tuple[int, ...]) -> int:
    """Chords of at most max_keys fingers that contain none of the blocked chords, counted by hand."""
    return sum(
        1 for c in range(1, 1024) if c.bit_count() <= max_keys and not any(c & b == b for b in blocked)
    )

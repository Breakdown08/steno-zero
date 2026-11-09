"""Builders of calibration logs and keyboard profiles shared by the keyboard, drill and price tests."""

import itertools
import json
from typing import Any

from steno_zero.keyboard import Blocked, KeyboardProfile
from steno_zero.trainer import chord_label

STARTED: str = "2026-11-10T09:00:00.000Z"
P1: KeyboardProfile = KeyboardProfile("test", "c", "2026-11-10T00:00:00.000Z", (Blocked(152, False),))
P2: KeyboardProfile = KeyboardProfile(
    "test", "c", "2026-11-10T00:00:00.000Z", (Blocked(7, False), Blocked(896, False))
)


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
    overrides: dict[int, list[int]] | None = None, session: str = "calibration-2026-11-10T09-00-00.000Z"
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
        "version": 1,
        "session": session,
        "started": STARTED,
        "finished": "2026-11-10T09:06:00.000Z",
        "user_agent": "pytest",
        "max_held": 3,
        "attempts": [
            {"target": t, "typed": ty, "down_ms": 100.0 * k, "up_ms": 100.0 * k + 50.5}
            for k, (t, ty) in enumerate(rows)
        ],
    }


def calibration_text(overrides: dict[int, list[int]] | None = None) -> str:
    return json.dumps(calibration_dict(overrides))


# The log of check 5: 152 never gets through (a key is lost), 7 gets 3, 3, 15, 24 fails once and then passes.
CHECK5: dict[int, list[int]] = {152: [24, 24, 24], 7: [3, 3, 15], 24: [8, 24]}


def profile_dict(blocked: list[tuple[int, bool]], name: str = "test") -> dict[str, Any]:
    return {
        "format": "steno-zero/keyboard-profile",
        "version": 1,
        "name": name,
        "session": "calibration-2026-11-10T09-00-00.000Z",
        "created": STARTED,
        "blocked": [{"chord": c, "label": chord_label(c), "unclear": u} for c, u in blocked],
    }

"""Plans and drill logs shared by the drill and price tests."""

import functools
import json
from typing import Any

from steno_zero.drill import drill_plan
from steno_zero.keyboard import KeyboardProfile

type Plan = tuple[tuple[int, ...], ...]

SHA: str = "ab" * 32


def pair_chords() -> list[int]:
    return [(1 << i) | (1 << j) for i in range(10) for j in range(i + 1, 10)]


def stratum_of(chord: int) -> tuple[int, int]:
    return chord.bit_count(), (chord & 31).bit_count()


@functools.cache
def plan_default() -> Plan:
    return drill_plan(0, 100, 100, 6)


@functools.cache
def plan_with(profile: KeyboardProfile) -> Plan:
    return drill_plan(0, 100, 100, 6, profile)


def drill_dict(presentations: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """The example of the drill log from the spec."""
    rows: list[dict[str, Any]] = (
        presentations
        if presentations is not None
        else [
            {"i": 0, "target": 17, "typed": 17, "shown_ms": 1000.0, "down_ms": 1450.2, "up_ms": 1610.7},
            {"i": 1, "target": 3, "typed": 7, "shown_ms": 1625.0, "down_ms": 2100.0, "up_ms": 2230.5},
        ]
    )
    return {
        "format": "steno-zero/drill-log",
        "version": 1,
        "session": "drill-7-2026-11-10T09-00-00.000Z",
        "seed": 0,
        "block": 7,
        "max_keys": 6,
        "keyboard": {"name": "laptop", "sha256": SHA},
        "started": "2026-11-10T09:00:00.000Z",
        "finished": "2026-11-10T09:03:12.400Z",
        "user_agent": "pytest",
        "max_held": 6,
        "presentations": rows,
    }


def drill_text() -> str:
    return json.dumps(drill_dict())

"""Builders of trainer logs shared by the trainer tests."""

import json
from typing import Any

from tests.layout_helpers import VM, layout_obj_of

type Row = tuple[int, int, int, int, float, float]  # phrase, pos, target, typed, down_ms, up_ms

STARTED: str = "2026-11-08T10:00:00.000Z"
EXAMPLE: list[Row] = [
    (0, 0, 72, 72, 0, 100),
    (0, 1, 8, 9, 150, 300),
    (0, 1, 8, 8, 400, 500),
    (0, 2, 72, 72, 550, 700),
    (0, 3, 8, 1023, 750, 900),
    (0, 3, 8, 8, 950, 1000),
]


def log_dict(
    rows: list[Row],
    session: str = "s1",
    started: str = STARTED,
    phrases: list[int] | None = None,
    chars: int = 4,
) -> dict[str, Any]:
    return {
        "format": "steno-zero/trainer-log",
        "version": 2,
        "session": session,
        "table": "rival",
        "table_sha256": "0" * 64,
        "started": started,
        "finished": "2026-11-08T10:02:31.412Z",
        "user_agent": "pytest",
        "layout": layout_obj_of(VM),
        "max_held": 3,
        "phrases": [0] if phrases is None else phrases,
        "chars": chars,
        "attempts": [
            {"phrase": ph, "pos": pos, "target": t, "typed": ty, "down_ms": d, "up_ms": u}
            for ph, pos, t, ty, d, u in rows
        ],
    }


def log_text(
    rows: list[Row],
    session: str = "s1",
    started: str = STARTED,
    phrases: list[int] | None = None,
    chars: int = 4,
) -> str:
    return json.dumps(log_dict(rows, session, started, phrases, chars))


def example_text() -> str:
    return log_text(EXAMPLE)

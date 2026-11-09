"""Checks 25-26: chord features, the features frame, the presentations frame."""

import pandas as pd
import pytest

from steno_zero.drill import DrillLog, Presentation
from steno_zero.price import (
    FEATURE_NAMES,
    chord_features,
    features_frame,
    logs_keyboard,
    presentations_frame,
)
from tests.drill_helpers import SHA

# chord: keys, left, right, both, index_pairs, adjacent, span, holes, mirror
TABLE: dict[int, tuple[int, ...]] = {
    1: (1, 1, 0, 0, 0, 0, 0, 0, 0),
    513: (2, 1, 1, 1, 0, 0, 0, 0, 1),
    9: (2, 2, 0, 0, 0, 0, 3, 2, 0),
    24: (2, 2, 0, 0, 1, 1, 0, 0, 0),
    18: (2, 2, 0, 0, 0, 0, 2, 1, 0),
    324: (3, 1, 2, 1, 0, 0, 2, 1, 0),
    1023: (10, 5, 5, 1, 2, 8, 6, 0, 1),
}
COLUMNS: tuple[str, ...] = (
    "keys",
    "left",
    "right",
    "both_hands",
    "index_pairs",
    "adjacent",
    "span",
    "holes",
    "mirror",
)


@pytest.mark.parametrize("chord", sorted(TABLE))
def test_chord_features_table(chord: int) -> None:
    features: dict[str, int] = chord_features(chord)
    assert list(features) == list(FEATURE_NAMES)
    expected: dict[str, int] = dict(zip(COLUMNS, TABLE[chord], strict=True))
    name: str
    for name in COLUMNS:
        assert features[name] == expected[name], name
    assert all(type(v) is int for v in features.values())
    assert [features[f"key_{i}"] for i in range(10)] == [chord >> i & 1 for i in range(10)]


@pytest.mark.parametrize("chord", [0, 1024, -1])
def test_chord_features_out_of_range(chord: int) -> None:
    with pytest.raises(ValueError):
        chord_features(chord)


def test_chord_features_invariants() -> None:
    chord: int
    for chord in range(1, 1024):
        f: dict[str, int] = chord_features(chord)
        assert f["keys"] == f["left"] + f["right"] == sum(f[f"key_{i}"] for i in range(10))
        assert f["keys"] == chord.bit_count()
        assert f["holes"] <= f["span"]
        assert 0 <= f["index_pairs"] <= 2
        assert f["both_hands"] == int(f["left"] > 0 and f["right"] > 0)
        if f["mirror"] == 1:
            assert f["left"] == f["right"]


def test_features_frame() -> None:
    frame: pd.DataFrame = features_frame([9, 1])
    assert list(frame.index) == [9, 1]
    assert frame.index.name == "chord"
    assert list(frame.columns) == list(FEATURE_NAMES)
    assert all(str(t) == "int64" for t in frame.dtypes)
    assert frame.loc[9, "holes"] == 2
    assert frame.loc[1, "keys"] == 1


def pres(rows: list[tuple[int, int]], start: float = 1000.0) -> tuple[Presentation, ...]:
    """(target, typed) rows; each takes 400 ms to type and starts 100 ms after the previous one."""
    out: list[Presentation] = []
    shown: float = start
    i: int
    target: int
    typed: int
    for i, (target, typed) in enumerate(rows):
        out.append(Presentation(i, target, typed, shown, shown + 100.0, shown + 400.0))
        shown += 500.0
    return tuple(out)


def log(
    session: str,
    started: str,
    rows: list[tuple[int, int]],
    keyboard: tuple[str, str] | None = None,
    block: int = 0,
) -> DrillLog:
    return DrillLog(
        session, 0, block, 6, keyboard, started, "2026-11-10T23:00:00.000Z", "pytest", 6, pres(rows)
    )


LATE: DrillLog = log("b", "2026-11-10T10:00:00.000Z", [(1, 1), (3, 3), (24, 8), (9, 9)], block=2)
EARLY: DrillLog = log("a", "2026-11-10T09:00:00.000Z", [(17, 17), (5, 5), (6, 7)], block=1)


def test_presentations_frame_columns_rows_and_values() -> None:
    frame: pd.DataFrame = presentations_frame([LATE, EARLY], 1)
    assert list(frame.columns) == [
        "session",
        "block",
        "started",
        "i",
        "target",
        "typed",
        "miss",
        "shown_ms",
        "down_ms",
        "up_ms",
        "total_ms",
        "motor_ms",
        *FEATURE_NAMES,
    ]
    assert list(frame["session"]) == ["a", "a", "b", "b", "b"]
    assert list(frame["i"]) == [1, 2, 1, 2, 3]
    assert list(frame["target"]) == [5, 6, 3, 24, 9]
    assert list(frame["block"]) == [1, 1, 2, 2, 2]
    assert list(frame["miss"]) == [False, True, False, True, False]
    assert list(frame["total_ms"]) == [400.0] * 5
    assert list(frame["motor_ms"]) == [300.0] * 5
    assert list(frame["shown_ms"]) == [1500.0, 2000.0, 1500.0, 2000.0, 2500.0]
    assert list(frame["up_ms"]) == [1900.0, 2400.0, 1900.0, 2400.0, 2900.0]
    row: int
    for row in range(5):
        expected: dict[str, int] = chord_features(int(frame["target"].iloc[row]))
        name: str
        for name in FEATURE_NAMES:
            assert frame[name].iloc[row] == expected[name], (row, name)
    assert frame.attrs["keyboard"] is None


def test_presentations_frame_remembers_the_keyboard() -> None:
    first: DrillLog = log("a", "2026-11-10T09:00:00.000Z", [(1, 1), (3, 3)], ("laptop", SHA))
    second: DrillLog = log("b", "2026-11-10T10:00:00.000Z", [(1, 1), (3, 3)], ("laptop", SHA))
    frame: pd.DataFrame = presentations_frame([first, second], 0)
    assert frame.attrs["keyboard"] == ("laptop", SHA)
    assert len(frame) == 4


def test_presentations_frame_errors() -> None:
    with pytest.raises(ValueError):
        presentations_frame([LATE, LATE], 1)
    with pytest.raises(ValueError):
        presentations_frame([], 1)
    with pytest.raises(ValueError):
        presentations_frame([LATE], -1)
    with pytest.raises(ValueError):
        presentations_frame([LATE, EARLY], 4)


def mixed() -> list[DrillLog]:
    kb: tuple[str, str] = ("laptop", SHA)
    return [
        log("a", "2026-11-10T09:00:00.000Z", [(1, 1), (3, 3)], kb),
        log("b", "2026-11-10T10:00:00.000Z", [(1, 1), (3, 3)], kb),
        log("c", "2026-11-10T11:00:00.000Z", [(1, 1), (3, 3)]),
        log("d", "2026-11-10T12:00:00.000Z", [(1, 1), (3, 3)]),
    ]


def test_presentations_frame_rejects_mixed_keyboards() -> None:
    info: pytest.ExceptionInfo[ValueError]
    with pytest.raises(ValueError) as info:
        presentations_frame(mixed(), 0)
    message: str = str(info.value)
    assert "different keyboards" in message
    assert "laptop" in message
    assert SHA[:8] in message
    assert "none" in message
    assert message.count("2 sessions") == 2


def test_logs_keyboard() -> None:
    assert logs_keyboard(mixed()[:2]) == ("laptop", SHA)
    assert logs_keyboard(mixed()[2:]) is None
    with pytest.raises(ValueError, match="different keyboards"):
        logs_keyboard(mixed())
    other: DrillLog = log("e", "2026-11-10T13:00:00.000Z", [(1, 1)], ("laptop", "cd" * 32))
    with pytest.raises(ValueError, match="different keyboards"):
        logs_keyboard([mixed()[0], other])

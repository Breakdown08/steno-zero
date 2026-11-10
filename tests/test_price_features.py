"""Checks 37-38: chord features, the features frame, the presentations frame with layouts."""

import pandas as pd
import pytest

from steno_zero.drill import DrillLog, Presentation
from steno_zero.layout import Layout
from steno_zero.price import (
    FEATURE_NAMES,
    FINGER,
    THUMB_INDEX,
    chord_features,
    features_frame,
    logs_keyboard,
    logs_layouts,
    presentations_frame,
)
from tests.drill_helpers import SHA
from tests.layout_helpers import FINGER_NAMES, VM, ZZ

# chord: fingers, left, right, both, thumb_index, adjacent, span, holes, mirror
TABLE: dict[int, tuple[int, ...]] = {
    1: (1, 1, 0, 0, 0, 0, 0, 0, 0),
    513: (2, 1, 1, 1, 0, 0, 0, 0, 1),
    9: (2, 2, 0, 0, 0, 0, 3, 2, 0),
    24: (2, 2, 0, 0, 1, 1, 1, 0, 0),
    18: (2, 2, 0, 0, 0, 0, 3, 2, 0),
    48: (2, 1, 1, 1, 0, 0, 0, 0, 1),
    96: (2, 0, 2, 0, 1, 1, 1, 0, 0),
    324: (3, 1, 2, 1, 0, 0, 2, 1, 0),
    1023: (10, 5, 5, 1, 2, 8, 8, 0, 1),
}
COLUMNS: tuple[str, ...] = (
    "fingers",
    "left",
    "right",
    "both_hands",
    "thumb_index",
    "adjacent",
    "span",
    "holes",
    "mirror",
)


def test_constants() -> None:
    assert FEATURE_NAMES == (
        "fingers",
        "left",
        "right",
        "both_hands",
        "L4",
        "L3",
        "L2",
        "L1",
        "L0",
        "R0",
        "R1",
        "R2",
        "R3",
        "R4",
        "thumb_index",
        "adjacent",
        "span",
        "holes",
        "mirror",
    )
    assert FINGER == (0, 1, 2, 3, 4, 4, 3, 2, 1, 0)
    assert THUMB_INDEX == ((3, 4), (5, 6))


def test_spec_examples() -> None:
    f24: dict[str, int] = chord_features(24)
    assert (f24["fingers"], f24["left"], f24["right"], f24["both_hands"]) == (2, 2, 0, 0)
    assert (f24["L1"], f24["L0"], f24["thumb_index"], f24["adjacent"]) == (1, 1, 1, 1)
    assert (f24["span"], f24["holes"], f24["mirror"]) == (1, 0, 0)
    f9: dict[str, int] = chord_features(9)
    assert (f9["span"], f9["holes"]) == (3, 2)
    f48: dict[str, int] = chord_features(48)
    assert (f48["mirror"], f48["thumb_index"]) == (1, 0)


@pytest.mark.parametrize("chord", sorted(TABLE))
def test_chord_features_table(chord: int) -> None:
    features: dict[str, int] = chord_features(chord)
    assert list(features) == list(FEATURE_NAMES)
    expected: dict[str, int] = dict(zip(COLUMNS, TABLE[chord], strict=True))
    name: str
    for name in COLUMNS:
        assert features[name] == expected[name], name
    assert all(type(v) is int for v in features.values())
    assert [features[name] for name in FINGER_NAMES] == [chord >> i & 1 for i in range(10)]


@pytest.mark.parametrize("chord", [0, 1024, -1])
def test_chord_features_out_of_range(chord: int) -> None:
    with pytest.raises(ValueError):
        chord_features(chord)


def test_chord_features_invariants() -> None:
    chord: int
    for chord in range(1, 1024):
        f: dict[str, int] = chord_features(chord)
        assert f["fingers"] == f["left"] + f["right"] == sum(f[name] for name in FINGER_NAMES)
        assert f["fingers"] == chord.bit_count()
        assert f["holes"] <= f["span"]
        assert 0 <= f["thumb_index"] <= 2
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
    assert frame.loc[1, "fingers"] == 1


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
    layout: Layout = VM,
) -> DrillLog:
    return DrillLog(
        session, 0, block, 6, layout, keyboard, started, "2026-11-10T23:00:00.000Z", "pytest", 6, pres(rows)
    )


LATE: DrillLog = log("b", "2026-11-10T10:00:00.000Z", [(1, 1), (3, 3), (24, 8), (9, 9)], block=2)
EARLY: DrillLog = log("a", "2026-11-10T09:00:00.000Z", [(17, 17), (5, 5), (6, 7)], block=1)


def test_presentations_frame_columns_rows_and_values() -> None:
    frame: pd.DataFrame = presentations_frame([LATE, EARLY], 1)
    assert list(frame.columns) == [
        "session",
        "block",
        "started",
        "layout",
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
    assert list(frame["layout"]) == ["qwerty-vm"] * 5
    assert frame.attrs["layouts"] == {"qwerty-vm": VM}


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


def test_presentations_frame_two_layouts() -> None:
    one: DrillLog = log("a", "2026-11-10T09:00:00.000Z", [(1, 1), (3, 3), (5, 5)], layout=VM)
    two: DrillLog = log("b", "2026-11-10T10:00:00.000Z", [(1, 1), (3, 3)], layout=ZZ)
    frame: pd.DataFrame = presentations_frame([two, one], 0)
    assert list(frame["session"]) == ["a", "a", "a", "b", "b"]
    assert list(frame["layout"]) == ["qwerty-vm"] * 3 + ["zz"] * 2
    assert frame.attrs["layouts"] == {"qwerty-vm": VM, "zz": ZZ}


def test_presentations_frame_same_layout_name_with_other_codes() -> None:
    other: Layout = Layout("qwerty-vm", ZZ.codes, ZZ.labels)
    one: DrillLog = log("a", "2026-11-10T09:00:00.000Z", [(1, 1), (3, 3)], layout=VM)
    two: DrillLog = log("b", "2026-11-10T10:00:00.000Z", [(1, 1), (3, 3)], layout=other)
    with pytest.raises(ValueError):
        presentations_frame([one, two], 0)


def test_logs_layouts() -> None:
    one: DrillLog = log("a", "2026-11-10T09:00:00.000Z", [(1, 1)], layout=ZZ)
    two: DrillLog = log("b", "2026-11-10T10:00:00.000Z", [(1, 1)], layout=VM)
    three: DrillLog = log("c", "2026-11-10T11:00:00.000Z", [(1, 1)], layout=VM)
    layouts: dict[str, Layout] = logs_layouts([one, two, three])
    assert list(layouts) == ["qwerty-vm", "zz"]
    assert layouts == {"qwerty-vm": VM, "zz": ZZ}
    other: DrillLog = log("d", "2026-11-10T12:00:00.000Z", [(1, 1)], layout=Layout("zz", VM.codes, VM.labels))
    with pytest.raises(ValueError):
        logs_layouts([one, other])

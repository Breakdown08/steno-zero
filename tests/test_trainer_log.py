"""Checks 19-25: exam log reading and statistics."""

import json
import random
from typing import Any

import pytest

from steno_zero.chords import neighbours
from steno_zero.trainer import (
    Attempt,
    ChordStats,
    SessionStats,
    TrainerLog,
    TrainerLogError,
    TrainerStats,
    read_trainer_log,
    trainer_stats,
)
from tests.trainer_helpers import EXAMPLE, STARTED, Row, example_text, log_dict, log_text

MISSING: object = object()


def corrupted(path: tuple[str | int, ...], value: object) -> str:
    data: dict[str, Any] = log_dict(EXAMPLE)
    node: Any = data
    key: str | int
    for key in path[:-1]:
        node = node[key]
    if value is MISSING:
        del node[path[-1]]
    else:
        node[path[-1]] = value
    return json.dumps(data)


# 19: reading


def test_read_example_log() -> None:
    log: TrainerLog = read_trainer_log(example_text())
    assert log.session == "s1"
    assert log.table == "rival"
    assert log.table_sha256 == "0" * 64
    assert log.started == STARTED
    assert log.finished == "2026-11-08T10:02:31.412Z"
    assert log.user_agent == "pytest"
    assert log.max_held == 3
    assert log.phrases == (0,)
    assert log.chars == 4
    assert log.attempts == tuple(Attempt(*row) for row in EXAMPLE)
    assert len(log.attempts) == 6


def test_read_ignores_extra_keys() -> None:
    data: dict[str, Any] = log_dict(EXAMPLE)
    data["extra"] = 1
    data["attempts"][0]["hint"] = True
    log: TrainerLog = read_trainer_log(json.dumps(data))
    assert log.attempts[0] == Attempt(*EXAMPLE[0])


# 20: errors

BAD: dict[str, str] = {
    "broken-json": '{"format": ',
    "root-list": "[]",
    "other-format": corrupted(("format",), "other"),
    "version-2": corrupted(("version",), 2),
    "no-session": corrupted(("session",), MISSING),
    "empty-session": corrupted(("session",), ""),
    "no-finished": corrupted(("finished",), MISSING),
    "max-held-11": corrupted(("max_held",), 11),
    "max-held-bool": corrupted(("max_held",), True),
    "chars-0": corrupted(("chars",), 0),
    "phrases-empty": corrupted(("phrases",), []),
    "phrases-negative": corrupted(("phrases",), [-1]),
    "attempts-empty": corrupted(("attempts",), []),
    "no-up-ms": corrupted(("attempts", 0, "up_ms"), MISSING),
    "phrase-negative": corrupted(("attempts", 0, "phrase"), -1),
    "phrase-bool": corrupted(("attempts", 0, "phrase"), True),
    "phrase-not-listed": corrupted(("attempts", 0, "phrase"), 5),
    "target-0": corrupted(("attempts", 0, "target"), 0),
    "typed-1024": corrupted(("attempts", 0, "typed"), 1024),
    "down-string": corrupted(("attempts", 0, "down_ms"), "1"),
    "up-bool": corrupted(("attempts", 0, "up_ms"), True),
    "down-after-up": corrupted(("attempts", 0, "down_ms"), 101),
    "up-decreases": log_text([*EXAMPLE[:2], (0, 1, 8, 8, 200, 250)]),
    "zero-duration": log_text([(0, 0, 8, 8, 100, 100)]),
}


@pytest.mark.parametrize("text", list(BAD.values()), ids=list(BAD))
def test_read_rejects(text: str) -> None:
    with pytest.raises(TrainerLogError):
        read_trainer_log(text)


def test_trainer_log_error_is_value_error() -> None:
    assert issubclass(TrainerLogError, ValueError)
    with pytest.raises(ValueError):
        read_trainer_log("[]")


# 21: the worked example


def test_stats_example() -> None:
    stats: TrainerStats = trainer_stats([read_trainer_log(example_text())])
    assert stats.attempts == 6
    assert stats.correct == 4
    assert stats.neighbour_misses == 1
    assert stats.other_misses == 1
    assert stats.slip_prob == pytest.approx(1 / 56)
    assert stats.median_ms == 200.0
    assert stats.chords == (
        ChordStats(8, "f", 4, 2, 0, None, ((9, 1), (1023, 1))),
        ChordStats(72, "f j", 2, 2, 1, 200.0, ()),
    )
    assert len(stats.sessions) == 1
    s: SessionStats = stats.sessions[0]
    assert (s.session, s.table, s.started) == ("s1", "rival", STARTED)
    assert (s.phrases, s.chars, s.attempts, s.misses) == (1, 4, 6, 2)
    assert s.time_s == pytest.approx(1.0)
    assert s.chars_per_min == pytest.approx(240.0)
    assert s.miss_rate == pytest.approx(1 / 3)


# 22-23: intervals


def test_intervals_do_not_cross_logs() -> None:
    a: TrainerLog = read_trainer_log(
        log_text([(0, 0, 8, 8, 100, 200), (0, 1, 8, 8, 250, 400)], "a", "2026-11-08T10:00:00.000Z")
    )
    b: TrainerLog = read_trainer_log(
        log_text([(0, 0, 8, 8, 0, 100), (0, 1, 8, 8, 150, 300)], "b", "2026-11-09T10:00:00.000Z")
    )
    first: TrainerStats = trainer_stats([b, a])
    second: TrainerStats = trainer_stats([a, b])
    stats: TrainerStats
    for stats in (first, second):
        assert [s.session for s in stats.sessions] == ["a", "b"]
        assert len(stats.chords) == 1
        chord: ChordStats = stats.chords[0]
        assert chord.chord == 8
        assert chord.intervals == 2
        assert chord.attempts == 4
        assert stats.median_ms == 200.0


def test_different_phrases_break_interval() -> None:
    log: TrainerLog = read_trainer_log(
        log_text([(0, 5, 8, 8, 0, 100), (1, 6, 8, 8, 150, 300)], phrases=[0, 1])
    )
    stats: TrainerStats = trainer_stats([log])
    assert stats.chords[0].intervals == 0
    assert stats.median_ms is None


# 24: random logs


def random_log(seed: int) -> TrainerLog:
    rng: random.Random = random.Random(seed)
    rows: list[Row] = []
    t: float = 0.0
    pos: int = 0
    phrase: int = 0
    i: int
    for i in range(50):
        target: int = rng.choice([8, 72, 1, 48, 1023, 300])
        typed: int = target
        if rng.random() >= 0.7:
            typed = rng.choice(neighbours(target)) if rng.random() < 0.5 else rng.randint(1, 1023)
        down: float = t + rng.uniform(10, 100)
        up: float = down + rng.uniform(50, 150)
        rows.append((phrase, pos, target, typed, down, up))
        t = up
        if i % 7 == 6:
            phrase = rng.randint(0, 2)
        if typed == target:
            pos += 1
    return read_trainer_log(
        log_text(
            rows,
            session=f"r{seed}",
            started=f"2026-11-0{seed + 1}T10:00:00.000Z",
            phrases=[0, 1, 2],
            chars=100,
        )
    )


def check_properties(logs: list[TrainerLog]) -> None:
    stats: TrainerStats = trainer_stats(logs)
    total: int = sum(len(log.attempts) for log in logs)
    assert stats.attempts == total
    assert stats.correct + stats.neighbour_misses + stats.other_misses == stats.attempts
    assert sum(c.attempts for c in stats.chords) == stats.attempts
    assert sum(s.attempts for s in stats.sessions) == stats.attempts
    assert 0 <= stats.slip_prob <= 1
    c: ChordStats
    for c in stats.chords:
        assert c.intervals <= c.correct <= c.attempts
        assert sum(n for _, n in c.typed) == c.attempts - c.correct
    by_session: dict[str, TrainerLog] = {log.session: log for log in logs}
    s: SessionStats
    for s in stats.sessions:
        log: TrainerLog = by_session[s.session]
        assert s.chars_per_min == pytest.approx(s.chars / s.time_s * 60)
        assert s.misses == len(log.attempts) - sum(1 for a in log.attempts if a.typed == a.target)


@pytest.mark.parametrize("seed", range(5))
def test_random_log_properties(seed: int) -> None:
    check_properties([random_log(seed)])


def test_random_logs_together() -> None:
    check_properties([random_log(s) for s in range(5)])


# 25: errors


def test_stats_empty() -> None:
    with pytest.raises(ValueError):
        trainer_stats([])


def test_stats_duplicate_session() -> None:
    log: TrainerLog = read_trainer_log(example_text())
    with pytest.raises(ValueError):
        trainer_stats([log, log])

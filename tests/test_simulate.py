"""Checks 17-23: simulator."""

import random

import pytest

from steno_zero.params import PenaltyParams
from steno_zero.rival import rival_table
from steno_zero.simulate import Score, Segmentation, decode, evaluate, segment
from steno_zero.table import Table
from tests.helpers import BASE, GREEDY_EXTRA, aa_table, costs, fragment, greedy_table


def test_working_example_segment_and_decode() -> None:
    t: Table = aa_table()
    c: tuple[int, ...] = costs()
    assert segment("аа", t, c) == Segmentation((72,), 230)
    assert segment("ааа", t, c) == Segmentation((72, 1), 470)
    assert decode((72, 1), t) == "ааа"


def test_working_example_evaluate() -> None:
    t: Table = aa_table()
    s: Score = evaluate("аа", t, costs(), PenaltyParams(), horizon=1000.0)
    assert s.chars == 2
    assert s.chords == 1
    assert s.typing_ms == 230
    assert s.t_char == pytest.approx(0.115)
    assert s.usage["аа"] == 1
    assert s.usage["а"] == 0
    assert s.memory == pytest.approx(7450.909090909091)
    assert s.confusion == pytest.approx(2.0)
    assert s.total == pytest.approx(7567.909090909091)


def test_greedy_not_optimal() -> None:
    t: Table = Table(BASE | {"аб": 72, "бв": 64})
    seg: Segmentation = segment("абв", t, costs())
    assert seg.chords == (72, 3)
    assert seg.total_ms == 525
    alternative: int = costs()[1] + costs()[64]
    assert alternative == 440
    assert seg.total_ms > alternative


def test_greedy_property() -> None:
    t: Table = greedy_table()
    c: tuple[int, ...] = costs()
    rng: random.Random = random.Random(0)
    pieces: list[str] = list(t.entries)
    _: int
    for _ in range(200):
        text: str = "".join(rng.choice("абв ") for _ in range(rng.randint(1, 12)))
        seg: Segmentation = segment(text, t, c)
        pos: int = 0
        chord: int
        for chord in seg.chords:
            p: str = t.piece(chord)
            assert text.startswith(p, pos)
            longer: list[str] = [q for q in pieces if len(q) > len(p) and text.startswith(q, pos)]
            assert longer == [], (text, pos)
            pos += len(p)
        assert pos == len(text)
        assert seg.total_ms == sum(c[ch] for ch in seg.chords)
    assert set(GREEDY_EXTRA) <= set(pieces)


def test_edge_cases() -> None:
    t: Table = aa_table()
    c: tuple[int, ...] = costs()
    assert segment("", t, c) == Segmentation((), 0)
    with pytest.raises(ValueError):
        segment("a", t, c)
    with pytest.raises(ValueError):
        decode((1000,), t)
    with pytest.raises(ValueError):
        evaluate("", t, c, PenaltyParams(), 1000.0)
    with pytest.raises(ValueError):
        evaluate("аа", t, c, PenaltyParams(), 0)


def test_lossless_on_fragment() -> None:
    text: str = fragment()
    c: tuple[int, ...] = costs()
    t: Table
    for t in (aa_table(), rival_table(text, c), greedy_table()):
        assert decode(segment(text, t, c).chords, t) == text


def test_usage_consistent() -> None:
    text: str = fragment()
    t: Table = greedy_table()
    s: Score = evaluate(text, t, costs(), PenaltyParams(), 1_000_000.0)
    assert s.chars == len(text)
    assert set(s.usage) == set(t.entries)
    assert sum(s.usage.values()) == s.chords
    assert s.chords < len(text)  # multi-symbol pieces were used on real text
    assert s.total == pytest.approx(1_000_000.0 * s.t_char + s.memory + s.confusion)

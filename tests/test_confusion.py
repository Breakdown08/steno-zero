"""Confusion penalty, checks 1-14: neighbours, params, neighbour_counts, evaluate."""

import dataclasses
import random

import pytest

from steno_zero.chords import N_CHORDS, neighbours
from steno_zero.evolve import random_table
from steno_zero.params import PenaltyParams
from steno_zero.rival import rival_table
from steno_zero.simulate import Score, evaluate, neighbour_counts
from steno_zero.table import Table
from tests.helpers import BASE, aa_table, base_table, costs, fragment, greedy_table

HORIZON: float = 1_000_000.0


def popcount(x: int) -> int:
    return bin(x).count("1")


def test_neighbours_examples() -> None:
    assert neighbours(1) == (3, 5, 9, 17, 33, 65, 129, 257, 513)
    assert neighbours(72) == (8, 64, 73, 74, 76, 88, 104, 200, 328, 584)
    assert neighbours(1023) == (511, 767, 895, 959, 991, 1007, 1015, 1019, 1021, 1022)


def test_neighbours_properties() -> None:
    table: dict[int, tuple[int, ...]] = {c: neighbours(c) for c in range(1, N_CHORDS + 1)}
    c: int
    for c in table:
        ns: tuple[int, ...] = table[c]
        assert list(ns) == sorted(ns)
        assert all(1 <= b <= N_CHORDS for b in ns)
        assert all(popcount(c ^ b) == 1 for b in ns)
        assert len(ns) == (9 if popcount(c) == 1 else 10), c
        assert all(c in table[b] for b in ns)


@pytest.mark.parametrize("bad", [0, 1024])
def test_neighbours_out_of_range(bad: int) -> None:
    with pytest.raises(ValueError):
        neighbours(bad)


def test_penalty_params_defaults() -> None:
    assert PenaltyParams() == PenaltyParams(
        entry_s=60.0, rarity_s=120.0, rarity_uses=50.0, slip_prob=0.002, confusion_s=2.0
    )
    assert list(dataclasses.asdict(PenaltyParams())) == [
        "entry_s",
        "rarity_s",
        "rarity_uses",
        "slip_prob",
        "confusion_s",
    ]


def test_neighbour_counts_base() -> None:
    counts: dict[str, int] = neighbour_counts(base_table())
    assert counts["а"] == 5
    assert counts["б"] == 5
    assert list(counts) == list(base_table().entries)


def test_neighbour_counts_matches_brute_force() -> None:
    tables: list[Table] = [greedy_table()]
    s: int
    for s in range(5):
        tables.append(random_table(fragment(), random.Random(s), 20))
    t: Table
    for t in tables:
        counts: dict[str, int] = neighbour_counts(t)
        assert list(counts) == list(t.entries)
        p: str
        for p in t.entries:
            expected: int = sum(1 for q in t.entries if q != p and popcount(t.chord(p) ^ t.chord(q)) == 1)
            assert counts[p] == expected, p


def test_neighbour_counts_no_neighbours() -> None:
    assert neighbour_counts(Table(BASE | {"аа": 1023}))["аа"] == 0


def test_evaluate_working_example() -> None:
    s: Score = evaluate("аа", aa_table(), costs(), PenaltyParams(), 1000.0)
    assert s.chars == 2
    assert s.chords == 1
    assert s.typing_ms == 230
    assert s.t_char == pytest.approx(0.115)
    assert s.usage["аа"] == 1
    assert s.memory == pytest.approx(7450.909090909091)
    assert s.confusion == pytest.approx(2.0)
    assert s.total == pytest.approx(7567.909090909091)


def test_evaluate_no_neighbours_is_free() -> None:
    s: Score = evaluate("аа", Table(BASE | {"аа": 1023}), costs(), PenaltyParams(), 1000.0)
    contrast: Score = evaluate("аа", aa_table(), costs(), PenaltyParams(), 1000.0)
    assert contrast.confusion > 0.0
    assert s.confusion == 0.0
    assert s.total == 1000.0 * s.t_char + s.memory


def test_evaluate_base_ab() -> None:
    s: Score = evaluate("аб", base_table(), costs(), PenaltyParams(), 1000.0)
    assert s.confusion == pytest.approx(20.0)


def fragment_scores(penalty: PenaltyParams) -> list[tuple[Table, Score]]:
    text: str = fragment()
    t: Table
    out: list[tuple[Table, Score]] = []
    for t in (greedy_table(), rival_table(text, costs())):
        out.append((t, evaluate(text, t, costs(), penalty, HORIZON)))
    return out


def test_formula_on_fragment() -> None:
    t: Table
    s: Score
    for t, s in fragment_scores(PenaltyParams()):
        counts: dict[str, int] = neighbour_counts(t)
        w: int = sum(s.usage[p] * counts[p] for p in t.entries)
        assert w > 0
        assert s.confusion == pytest.approx(0.002 * 2.0 * HORIZON * w / s.chars)
        assert s.total == pytest.approx(HORIZON * s.t_char + s.memory + s.confusion)


@pytest.mark.parametrize("off", [PenaltyParams(confusion_s=0.0), PenaltyParams(slip_prob=0.0)])
def test_switched_off_bitwise(off: PenaltyParams) -> None:
    base: list[tuple[Table, Score]] = fragment_scores(PenaltyParams())
    zero: list[tuple[Table, Score]] = fragment_scores(off)
    i: int
    for i in range(len(base)):
        s: Score = zero[i][1]
        ref: Score = base[i][1]
        assert ref.confusion > 0.0
        assert s.confusion == 0.0
        assert s.total == HORIZON * s.t_char + s.memory
        assert s.memory == ref.memory
        assert s.t_char == ref.t_char
        assert s.usage == ref.usage


def test_linearity() -> None:
    t: Table = greedy_table()
    base: Score = evaluate(fragment(), t, costs(), PenaltyParams(), HORIZON)
    assert base.confusion > 0.0
    twice_s: Score = evaluate(fragment(), t, costs(), PenaltyParams(confusion_s=4.0), HORIZON)
    twice_p: Score = evaluate(fragment(), t, costs(), PenaltyParams(slip_prob=0.004), HORIZON)
    assert twice_s.confusion == pytest.approx(2 * base.confusion)
    assert twice_p.confusion == pytest.approx(2 * base.confusion)


def test_payer_is_the_typed_entry() -> None:
    t: Table = Table(BASE | {"аа": 72})
    frequent: Score = evaluate("аа", t, costs(), PenaltyParams(), 1000.0)
    rare: Score = evaluate("ж", t, costs(), PenaltyParams(), 1000.0)
    assert frequent.confusion == pytest.approx(2.0)
    assert rare.confusion == pytest.approx(24.0)


@pytest.mark.parametrize(
    "bad",
    [PenaltyParams(slip_prob=-0.1), PenaltyParams(slip_prob=1.5), PenaltyParams(confusion_s=-1.0)],
)
def test_evaluate_rejects_bad_penalty(bad: PenaltyParams) -> None:
    with pytest.raises(ValueError):
        evaluate("аа", aa_table(), costs(), bad, 1000.0)


def test_evaluate_accepts_edge_slip() -> None:
    full: Score = evaluate("аа", aa_table(), costs(), PenaltyParams(slip_prob=1.0), 1000.0)
    none: Score = evaluate("аа", aa_table(), costs(), PenaltyParams(slip_prob=0.0), 1000.0)
    assert full.confusion == pytest.approx(1.0 * 2.0 * 1000.0 * 1 / 2)
    assert none.confusion == 0.0

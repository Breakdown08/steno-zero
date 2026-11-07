"""Key limit, checks 1-17: allowed_chords, Table.over_keys, rival, random_table, mutate, evolve."""

import dataclasses
import random

import pytest

from steno_zero.alphabet import ALPHABET
from steno_zero.chords import N_CHORDS, allowed_chords, chord_keys
from steno_zero.evolve import MUTATIONS, EvolveParams, EvolveResult, evolve, mutate, random_table
from steno_zero.params import DEFAULT_MAX_KEYS, PenaltyParams
from steno_zero.rival import rival_table
from steno_zero.table import Table
from tests.helpers import BASE, base_table, costs, fragment

HORIZON: float = 1_000_000.0
WIDE: dict[str, int] = BASE | {"аа": 1023}


def keys_in(chord: int) -> int:
    return len(chord_keys(chord))


# allowed_chords


def test_allowed_chords_examples() -> None:
    assert allowed_chords(10) == tuple(range(1, 1024))
    assert len(allowed_chords(6)) == 847
    assert len(allowed_chords(2)) == 55
    assert allowed_chords(2)[:8] == (1, 2, 3, 4, 5, 6, 8, 9)


def test_default_max_keys() -> None:
    assert DEFAULT_MAX_KEYS == 6
    assert len(allowed_chords(DEFAULT_MAX_KEYS)) == 847


@pytest.mark.parametrize("k", range(2, 11))
def test_allowed_chords_exact(k: int) -> None:
    got: tuple[int, ...] = allowed_chords(k)
    assert isinstance(got, tuple)
    assert all(a < b for a, b in zip(got, got[1:], strict=False))
    assert all(1 <= c <= N_CHORDS and keys_in(c) <= k for c in got)
    expected: list[int] = [c for c in range(1, N_CHORDS + 1) if keys_in(c) <= k]
    assert list(got) == expected


@pytest.mark.parametrize("bad", [0, 1, 11, -1])
def test_allowed_chords_out_of_range(bad: int) -> None:
    with pytest.raises(ValueError):
        allowed_chords(bad)


# Table.over_keys


def test_over_keys_base() -> None:
    t: Table = base_table()
    assert t.over_keys(6) == []
    assert t.over_keys(5) == []
    assert t.over_keys(4) == ["э"]
    assert t.over_keys(3) == ["н", "х", "щ", "ы", "ь", "э", "?"]


def test_over_keys_wide() -> None:
    t: Table = Table(WIDE)
    assert t.over_keys(6) == ["аа"]
    assert t.over_keys(10) == []


def test_over_keys_order_is_by_chord() -> None:
    # "аа" on chord 1023 sorts after "э" (31): entries order, not insertion order.
    t: Table = Table({"аа": 1023} | BASE)
    assert t.over_keys(4) == ["э", "аа"]


@pytest.mark.parametrize("bad", [0, 1, 11])
def test_over_keys_out_of_range(bad: int) -> None:
    with pytest.raises(ValueError):
        base_table().over_keys(bad)


# rival_table


def test_rival_same_for_k_from_3() -> None:
    text: str = fragment()
    default: Table = rival_table(text, costs())
    assert default.over_keys(3) == []
    assert rival_table(text, costs(), 10) == default
    assert rival_table(text, costs(), 6) == default
    assert rival_table(text, costs(), 3) == default


def test_rival_k2() -> None:
    t: Table = rival_table(fragment(), costs(), 2)
    assert t.over_keys(2) == []
    assert len(t) == 41


@pytest.mark.parametrize("bad", [0, 1, 11])
def test_rival_out_of_range(bad: int) -> None:
    with pytest.raises(ValueError):
        rival_table(fragment(), costs(), bad)


# random_table, mutate, EvolveParams


@pytest.mark.parametrize("k", [2, 3, 6])
def test_random_table_respects_limit(k: int) -> None:
    seed: int
    for seed in range(5):
        t: Table = random_table(fragment(), random.Random(seed), 20, k)
        assert t.over_keys(k) == []
        assert {p for p in t.entries if len(p) == 1} == set(ALPHABET)


def test_random_table_default_is_six() -> None:
    seed: int
    for seed in range(5):
        assert random_table(fragment(), random.Random(seed), 20).over_keys(6) == []


@pytest.mark.parametrize("bad", [0, 1, 11])
def test_random_table_out_of_range(bad: int) -> None:
    with pytest.raises(ValueError):
        random_table(fragment(), random.Random(0), 20, bad)


@pytest.mark.parametrize("bad", [1, 11])
@pytest.mark.parametrize("kind", ["add", "move"])
def test_mutate_out_of_range(kind: str, bad: int) -> None:
    with pytest.raises(ValueError):
        mutate(base_table(), kind, fragment(), random.Random(0), bad)


@pytest.mark.parametrize("k", [2, 6])
def test_mutation_chain_respects_limit(k: int) -> None:
    text: str = fragment()
    rng: random.Random = random.Random(0)
    t: Table = random_table(text, rng, 20, k)
    assert t.over_keys(k) == []
    i: int
    for i in range(300):  # noqa: B007
        t = mutate(t, rng.choice(MUTATIONS), text, rng, k)
        assert t.over_keys(k) == [], i
    if k == 2:
        assert len(t) <= 55


@pytest.mark.parametrize("kind", ["add", "move"])
def test_mutate_adds_no_violation_to_wide_table(kind: str) -> None:
    t: Table = Table(WIDE)
    rng: random.Random = random.Random(0)
    old: set[int] = set(t.entries.values())
    fresh: int = 0
    i: int
    for i in range(50):  # noqa: B007
        r: Table = mutate(t, kind, fragment(), rng, 6)
        c: int
        for c in set(r.entries.values()) - old:
            fresh += 1
            assert keys_in(c) <= 6
    assert fresh >= 1


def test_mutate_full_allowed_set_returns_table_unchanged() -> None:
    pieces: list[str] = [a + b for a in ALPHABET for b in ALPHABET][:14]
    names: list[str] = [*ALPHABET, *pieces]
    chords: tuple[int, ...] = allowed_chords(2)
    assert len(names) == len(chords) == 55
    t: Table = Table(dict(zip(names, chords, strict=True)))
    assert mutate(t, "add", fragment(), random.Random(0), 2) == t
    assert mutate(t, "move", fragment(), random.Random(0), 2) == t


def test_params_max_keys() -> None:
    assert EvolveParams().max_keys == 6
    assert list(dataclasses.asdict(EvolveParams()))[-1] == "max_keys"
    assert EvolveParams(max_keys=2).max_keys == 2
    assert EvolveParams(max_keys=10).max_keys == 10
    with pytest.raises(ValueError):
        EvolveParams(max_keys=1)
    with pytest.raises(ValueError):
        EvolveParams(max_keys=11)


# evolve


def run(params: EvolveParams, workers: int = 1) -> EvolveResult:
    return evolve(fragment(), costs(), PenaltyParams(), HORIZON, params, workers=workers)


def test_evolve_default_limit() -> None:
    res: EvolveResult = run(EvolveParams(seed=0, population=8, generations=10))
    assert res.best.over_keys(6) == []


def test_evolve_limit_three() -> None:
    res: EvolveResult = run(EvolveParams(seed=0, population=8, generations=10, max_keys=3))
    assert res.best.over_keys(3) == []


def test_evolve_workers_equal_with_limit() -> None:
    params: EvolveParams = EvolveParams(seed=0, population=8, generations=5, max_keys=4)
    one: EvolveResult = run(params, workers=1)
    two: EvolveResult = run(params, workers=2)
    assert one.history == two.history
    assert one.best == two.best
    assert one.best.over_keys(4) == []

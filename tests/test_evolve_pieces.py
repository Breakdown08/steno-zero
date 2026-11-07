"""Checks 1-15: fitness_text, draw_piece, random_table, mutate, EvolveParams."""

import random

import pytest

from steno_zero.alphabet import ALPHABET
from steno_zero.corpus import split_corpus
from steno_zero.evolve import (
    MUTATIONS,
    SAMPLE_CHARS,
    SAMPLE_CHUNKS,
    EvolveParams,
    draw_piece,
    fitness_text,
    mutate,
    random_table,
)
from steno_zero.params import MAX_PIECE_LEN
from steno_zero.table import Table
from tests.helpers import base_table, fragment


def train_text() -> str:
    return split_corpus(fragment(), 0.1)[0]


def long_entries(t: Table) -> dict[str, int]:
    return {p: c for p, c in t.entries.items() if len(p) >= 2}


def sample_table() -> Table:
    seed: int
    for seed in [3, *range(100)]:
        t: Table = random_table(fragment(), random.Random(seed), 20)
        if long_entries(t):
            return t
    raise AssertionError("no seed gives a table with long entries")


# 1-3 fitness_text


def test_fitness_text_example_and_whole() -> None:
    assert fitness_text("абвгдеёжзи", 4, 2) == "абеё"
    t: str = fragment()
    assert fitness_text(t, 0) == t
    assert fitness_text(t, len(t)) == t
    assert fitness_text(t, len(t) + 5) == t


def test_fitness_text_chunks() -> None:
    train: str = train_text()
    out: str = fitness_text(train, 1000, 20)
    assert len(out) == 1000
    i: int
    for i in range(20):
        s: int = i * len(train) // 20
        assert out[i * 50 : (i + 1) * 50] == train[s : s + 50]


def test_fitness_text_errors() -> None:
    with pytest.raises(ValueError):
        fitness_text(fragment(), -1)
    with pytest.raises(ValueError):
        fitness_text(fragment(), 100, 0)
    with pytest.raises(ValueError):
        fitness_text("абвгд", 3, 4)


# 4 draw_piece


def test_draw_piece() -> None:
    text: str = fragment()
    rng: random.Random = random.Random(0)
    lengths: set[int] = set()
    _: int
    for _ in range(500):
        p: str = draw_piece(text, rng)
        assert p in text
        assert 2 <= len(p) <= MAX_PIECE_LEN
        lengths.add(len(p))
    assert len(lengths) > 1


def test_draw_piece_short_text() -> None:
    with pytest.raises(ValueError):
        draw_piece("а", random.Random(0))


# 5-7 random_table


def test_random_table_shape() -> None:
    text: str = fragment()
    s: int
    for s in range(20):
        t: Table = random_table(text, random.Random(s), 20)
        assert isinstance(t, Table)
        entries: dict[str, int] = t.entries
        singles: set[str] = {p for p in entries if len(p) == 1}
        assert singles == set(ALPHABET)
        longs: dict[str, int] = long_entries(t)
        assert len(longs) <= 20
        assert all(p in text for p in longs)


def test_random_table_extra_zero_and_difference() -> None:
    text: str = fragment()
    assert len(random_table(text, random.Random(0), 0)) == 41
    assert random_table(text, random.Random(0), 20) != random_table(text, random.Random(1), 20)
    with pytest.raises(ValueError):
        random_table(text, random.Random(0), -1)


def test_random_table_same_seed() -> None:
    text: str = fragment()
    assert random_table(text, random.Random(7), 20) == random_table(text, random.Random(7), 20)


# 8-13 mutate


def test_mutate_add() -> None:
    text: str = fragment()
    t: Table = sample_table()
    rng: random.Random = random.Random(0)
    added: int = 0
    _: int
    for _ in range(200):
        r: Table = mutate(t, "add", text, rng)
        old: dict[str, int] = t.entries
        new: dict[str, int] = r.entries
        assert all(new[p] == c for p, c in old.items())
        fresh: list[str] = [p for p in new if p not in old]
        assert len(fresh) <= 1
        if fresh:
            added += 1
            assert fresh[0] in text
            assert len(fresh[0]) >= 2
            assert new[fresh[0]] not in old.values()
    assert added >= 1


def test_mutate_remove() -> None:
    text: str = fragment()
    b: Table = base_table()
    assert mutate(b, "remove", text, random.Random(0)) == b
    t: Table = sample_table()
    rng: random.Random = random.Random(0)
    _: int
    for _ in range(20):
        r: Table = mutate(t, "remove", text, rng)
        old: dict[str, int] = t.entries
        new: dict[str, int] = r.entries
        assert len(new) == len(old) - 1
        gone: list[str] = [p for p in old if p not in new]
        assert len(gone) == 1
        assert len(gone[0]) >= 2
        assert all(new[p] == c for p, c in old.items() if p != gone[0])


def test_mutate_swap() -> None:
    text: str = fragment()
    t: Table = sample_table()
    rng: random.Random = random.Random(0)
    _: int
    for _ in range(20):
        r: Table = mutate(t, "swap", text, rng)
        old: dict[str, int] = t.entries
        new: dict[str, int] = r.entries
        assert set(new) == set(old)
        assert set(new.values()) == set(old.values())
        changed: list[str] = [p for p in old if new[p] != old[p]]
        assert len(changed) == 2
        assert new[changed[0]] == old[changed[1]]
        assert new[changed[1]] == old[changed[0]]


def test_mutate_move() -> None:
    text: str = fragment()
    t: Table = sample_table()
    rng: random.Random = random.Random(0)
    _: int
    for _ in range(20):
        r: Table = mutate(t, "move", text, rng)
        old: dict[str, int] = t.entries
        new: dict[str, int] = r.entries
        assert set(new) == set(old)
        changed: list[str] = [p for p in old if new[p] != old[p]]
        assert len(changed) == 1
        assert new[changed[0]] not in old.values()


def test_mutate_on_full_table() -> None:
    pieces: list[str] = [a + b for a in ALPHABET for b in ALPHABET][:982]
    entries: dict[str, int] = {p: i + 1 for i, p in enumerate([*ALPHABET, *pieces])}
    assert len(entries) == 1023
    full: Table = Table(entries)
    rng: random.Random = random.Random(0)
    assert mutate(full, "add", fragment(), rng) == full
    assert mutate(full, "move", fragment(), rng) == full


def test_mutate_pure_and_unknown_kind() -> None:
    text: str = fragment()
    t: Table = sample_table()
    rng: random.Random = random.Random(0)
    before: dict[str, int] = t.entries
    kind: str
    for kind in MUTATIONS:
        mutate(t, kind, text, rng)
        assert t.entries == before
    with pytest.raises(ValueError):
        mutate(t, "crossover", text, rng)


# 14-15 EvolveParams


def test_params_defaults_and_constants() -> None:
    assert EvolveParams() == EvolveParams(
        seed=0, population=32, generations=300, elite=2, tournament=5, init_extra=20, max_mutations=3
    )
    assert SAMPLE_CHARS == 60_000
    assert SAMPLE_CHUNKS == 20
    assert MUTATIONS == ("add", "remove", "swap", "move")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"population": 1, "elite": 0, "tournament": 1},
        {"elite": -1},
        {"elite": 32},
        {"tournament": 0},
        {"tournament": 33},
        {"generations": -1},
        {"init_extra": -1},
        {"max_mutations": 0},
    ],
)
def test_params_validation(kwargs: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        EvolveParams(**kwargs)

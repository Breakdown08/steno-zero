"""Checks 24-27: rival."""

import itertools
import random
from collections import Counter

import pytest

from steno_zero.alphabet import ALPHABET
from steno_zero.rival import optimal_assignment, rival_table, symbol_counts
from steno_zero.table import Table
from tests.helpers import costs, fragment


def test_optimal_assignment_example() -> None:
    options: list[tuple[int, int]] = [(10, 300), (11, 100), (12, 200), (13, 100)]
    assert optimal_assignment([5, 1, 3], options) == [11, 12, 13]


def test_optimal_assignment_too_few_options() -> None:
    with pytest.raises(ValueError):
        optimal_assignment([1, 2, 3], [(1, 100), (2, 200)])


def test_optimal_assignment_matches_brute_force() -> None:
    rng: random.Random = random.Random(0)
    _: int
    for _ in range(50):
        n: int = rng.randint(1, 5)
        m: int = rng.randint(n, 7)
        weights: list[int] = [rng.randint(0, 20) for _ in range(n)]
        chords: list[int] = rng.sample(range(1, 1024), m)
        options: list[tuple[int, int]] = [(ch, rng.randint(1, 500)) for ch in chords]
        result: list[int] = optimal_assignment(weights, options)
        price: dict[int, int] = dict(options)
        assert len(result) == n
        assert len(set(result)) == n
        assert set(result) <= set(price)
        got: int = sum(w * price[ch] for w, ch in zip(weights, result, strict=True))
        best: int = min(
            sum(w * options[j][1] for w, j in zip(weights, perm, strict=True))
            for perm in itertools.permutations(range(m), n)
        )
        assert got == best


def test_symbol_counts() -> None:
    text: str = fragment()
    counts: dict[str, int] = symbol_counts(text)
    assert list(counts) == list(ALPHABET)
    assert sum(counts.values()) == len(text)
    ref: Counter[str] = Counter(text)
    assert all(counts[ch] == ref[ch] for ch in ALPHABET)


def test_rival_table_on_fragment() -> None:
    text: str = fragment()
    t: Table = rival_table(text, costs())
    assert len(t) == 41
    assert all(len(p) == 1 for p in t.entries)
    assert set(t.entries) == set(ALPHABET)
    counts: dict[str, int] = symbol_counts(text)
    top: list[str] = sorted(ALPHABET, key=lambda ch: (-counts[ch], ALPHABET.index(ch)))[:3]
    assert (
        counts[top[0]]
        > counts[top[1]]
        > counts[top[2]]
        > counts[sorted(ALPHABET, key=lambda ch: -counts[ch])[3]]
    )
    assert [t.chord(p) for p in top] == [8, 64, 4]

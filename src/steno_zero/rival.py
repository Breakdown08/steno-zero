"""Frequency rival."""

from collections.abc import Sequence

from steno_zero.alphabet import ALPHABET
from steno_zero.chords import N_CHORDS
from steno_zero.table import Table


def symbol_counts(text: str) -> dict[str, int]:
    counts: dict[str, int] = dict.fromkeys(ALPHABET, 0)
    ch: str
    for ch in text:
        if ch in counts:
            counts[ch] += 1
    return counts


def optimal_assignment(weights: Sequence[int], options: Sequence[tuple[int, int]]) -> list[int]:
    if len(options) < len(weights):
        raise ValueError("fewer options than weights")
    order: list[int] = sorted(range(len(weights)), key=lambda i: (-weights[i], i))
    ranked: list[tuple[int, int]] = sorted(options, key=lambda o: (o[1], o[0]))
    result: list[int] = [0] * len(weights)
    rank: int
    index: int
    for rank, index in enumerate(order):
        result[index] = ranked[rank][0]
    return result


def rival_table(text: str, costs: Sequence[int]) -> Table:
    counts: dict[str, int] = symbol_counts(text)
    symbols: list[str] = list(counts)
    options: list[tuple[int, int]] = [(c, costs[c]) for c in range(1, N_CHORDS + 1)]
    chords: list[int] = optimal_assignment([counts[s] for s in symbols], options)
    return Table(dict(zip(symbols, chords, strict=True)))

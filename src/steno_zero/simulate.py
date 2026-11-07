"""Typing simulator."""

from collections.abc import Sequence
from dataclasses import dataclass

from steno_zero.alphabet import ALPHABET
from steno_zero.chords import neighbours
from steno_zero.params import PenaltyParams
from steno_zero.table import Table


@dataclass(frozen=True)
class Segmentation:
    chords: tuple[int, ...]
    total_ms: int


@dataclass(frozen=True)
class Score:
    chars: int
    chords: int
    typing_ms: int
    t_char: float
    memory: float
    confusion: float
    total: float
    usage: dict[str, int]


def _pieces(text: str, table: Table) -> list[str]:
    bad: set[str] = set(text) - set(ALPHABET)
    if bad:
        raise ValueError(f"symbols outside the alphabet: {sorted(bad)!r}")
    entries: dict[str, int] = table.entries
    top: int = table.max_len()
    n: int = len(text)
    out: list[str] = []
    i: int = 0
    while i < n:
        length: int
        for length in range(min(top, n - i), 0, -1):
            piece: str = text[i : i + length]
            if piece in entries:
                out.append(piece)
                i += length
                break
        else:  # pragma: no cover - single-symbol entries are guaranteed by Table
            raise ValueError("no piece matches")
    return out


def segment(text: str, table: Table, costs: Sequence[int]) -> Segmentation:
    chords: tuple[int, ...] = tuple(table.chord(p) for p in _pieces(text, table))
    return Segmentation(chords, sum(costs[c] for c in chords))


def decode(chords: Sequence[int], table: Table) -> str:
    parts: list[str] = []
    c: int
    for c in chords:
        try:
            parts.append(table.piece(c))
        except KeyError:
            raise ValueError(f"unknown chord {c}") from None
    return "".join(parts)


def neighbour_counts(table: Table) -> dict[str, int]:
    taken: set[int] = {table.chord(p) for p in table.entries}
    counts: dict[str, int] = {}
    p: str
    for p in table.entries:
        counts[p] = sum(1 for c in neighbours(table.chord(p)) if c in taken)
    return counts


def evaluate(text: str, table: Table, costs: Sequence[int], penalty: PenaltyParams, horizon: float) -> Score:
    if text == "":
        raise ValueError("empty text")
    if horizon <= 0:
        raise ValueError("horizon must be positive")
    if not 0.0 <= penalty.slip_prob <= 1.0:
        raise ValueError("slip_prob must be within 0..1")
    if penalty.confusion_s < 0:
        raise ValueError("confusion_s must not be negative")
    pieces: list[str] = _pieces(text, table)
    usage: dict[str, int] = dict.fromkeys(table.entries, 0)
    typing_ms: int = 0
    p: str
    for p in pieces:
        usage[p] += 1
        typing_ms += costs[table.chord(p)]
    chars: int = len(text)
    t_char: float = typing_ms / 1000 / chars
    memory: float = 0.0
    n: int
    for n in usage.values():
        uses: float = horizon * n / chars
        memory += penalty.entry_s + penalty.rarity_s * penalty.rarity_uses / (penalty.rarity_uses + uses)
    confusion: float = 0.0
    if penalty.slip_prob != 0.0 and penalty.confusion_s != 0.0:
        weight: int = sum(usage[p] * k for p, k in neighbour_counts(table).items())
        confusion = penalty.slip_prob * penalty.confusion_s * horizon * weight / chars
    total: float = (horizon * t_char + memory) + confusion
    return Score(chars, len(pieces), typing_ms, t_char, memory, confusion, total, usage)

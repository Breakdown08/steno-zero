"""Shared constants and loaders for the tests. No network."""

import functools
import json
from pathlib import Path

from steno_zero.alphabet import ALPHABET
from steno_zero.chords import chord_costs
from steno_zero.params import CostParams
from steno_zero.table import Table

ROOT: Path = Path(__file__).resolve().parents[1]
FRAGMENT_PATH: Path = ROOT / "tests" / "data" / "fragment.txt"
BASE: dict[str, int] = {ALPHABET[i]: i + 1 for i in range(41)}
GREEDY_EXTRA: dict[str, int] = {"аб": 72, "бв": 64, "ба": 96, "б ": 68, "аба": 136, "абв ": 160}
SUMMARY_KEYS: set[str] = {"chars", "chords", "entries", "t_char", "memory", "total"}


@functools.cache
def fragment() -> str:
    """The fixture text, the way load_corpus returns it: one line, no trailing newline."""
    return FRAGMENT_PATH.read_text(encoding="utf-8").removesuffix("\n")


def costs() -> tuple[int, ...]:
    return chord_costs(CostParams())


def base_table() -> Table:
    return Table(BASE)


def aa_table() -> Table:
    return Table(BASE | {"аа": 72})


def greedy_table() -> Table:
    return Table(BASE | GREEDY_EXTRA)


def table_json(entries: dict[str, int]) -> str:
    """Raw table JSON written by hand, so that it can hold what Table would refuse."""
    rows: list[dict[str, object]] = [{"piece": p, "chord": c} for p, c in entries.items()]
    return json.dumps({"format": "steno-zero/table", "version": 1, "entries": rows}, ensure_ascii=False)

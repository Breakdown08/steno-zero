"""Checks 13-16: Table."""

import json
from typing import Any

import pytest

from steno_zero.alphabet import ALPHABET
from steno_zero.params import MAX_PIECE_LEN
from steno_zero.table import Table, TableError
from tests.helpers import BASE, aa_table, table_json

BAD: dict[str, dict[str, int]] = {
    "missing_symbol": {p: c for p, c in BASE.items() if p != "я"},
    "shared_chord": BASE | {"аа": 1},
    "chord_zero": BASE | {"а": 0},
    "chord_1024": BASE | {"а": 1024},
    "chord_bool": BASE | {"а": True},
    "empty_piece": BASE | {"": 100},
    "latin_piece": BASE | {"a": 100},
    "too_long": BASE | {"а" * (MAX_PIECE_LEN + 1): 100},
}


def test_table_error_is_value_error() -> None:
    assert issubclass(TableError, ValueError)


@pytest.mark.parametrize("name", sorted(BAD))
def test_table_rejects(name: str) -> None:
    with pytest.raises(TableError):
        Table(BAD[name])


def test_table_accepts_longest_piece() -> None:
    t: Table = Table(BASE | {"а" * MAX_PIECE_LEN: 100})
    assert t.max_len() == MAX_PIECE_LEN
    assert len(t) == 42


def test_json_round_trip_and_format() -> None:
    t: Table = aa_table()
    text: str = t.to_json()
    assert Table.from_json(text) == t
    assert text.endswith("\n")
    assert "  " in text.splitlines()[1]  # indent=2
    assert "а" in text  # ensure_ascii=False
    data: dict[str, Any] = json.loads(text)
    assert data["format"] == "steno-zero/table"
    assert data["version"] == 1
    chords: list[int] = [e["chord"] for e in data["entries"]]
    assert chords == sorted(chords)
    assert len(chords) == 42
    assert {e["piece"]: e["chord"] for e in data["entries"]} == BASE | {"аа": 72}


def test_from_json_rejects() -> None:
    no_entries: str = json.dumps({"format": "steno-zero/table", "version": 1})
    dup: str = table_json(BASE | {"аа": 1})
    bad: str
    for bad in ("{", no_entries, dup):
        with pytest.raises(TableError):
            Table.from_json(bad)


def test_entries_is_a_copy() -> None:
    t: Table = aa_table()
    d: dict[str, int] = t.entries
    d["ббб"] = 999
    d["а"] = 500
    del d["аа"]
    assert "ббб" not in t.entries
    assert t.entries["а"] == 1
    assert t == aa_table()


def test_entries_sorted_by_chord() -> None:
    chords: list[int] = list(aa_table().entries.values())
    assert chords == sorted(chords)


def test_accessors() -> None:
    t: Table = aa_table()
    assert t.chord("аа") == 72
    assert t.piece(72) == "аа"
    assert t.piece(1) == "а"
    assert t.max_len() == 2
    assert len(t) == 42
    with pytest.raises(KeyError):
        t.chord("ббб")
    with pytest.raises(KeyError):
        t.piece(1000)


def test_equality_and_rebuild() -> None:
    t: Table = aa_table()
    assert Table(t.entries | {"бб": 100}) != t
    assert Table(t.entries) == t
    assert len(ALPHABET) == len(Table(BASE))

"""Chord table."""

import json
from collections.abc import Mapping
from typing import Any

from steno_zero.alphabet import ALPHABET
from steno_zero.chords import N_CHORDS
from steno_zero.params import MAX_PIECE_LEN

FORMAT: str = "steno-zero/table"
VERSION: int = 1


class TableError(ValueError): ...


class Table:
    def __init__(self, entries: Mapping[str, int]) -> None:
        by_chord: dict[int, str] = {}
        piece: str
        chord: int
        for piece, chord in entries.items():
            if not isinstance(piece, str) or piece == "":
                raise TableError("piece must be a non-empty string")
            if len(piece) > MAX_PIECE_LEN:
                raise TableError(f"piece {piece!r} is longer than {MAX_PIECE_LEN}")
            if any(ch not in ALPHABET for ch in piece):
                raise TableError(f"piece {piece!r} has a symbol outside the alphabet")
            if type(chord) is not int or not 1 <= chord <= N_CHORDS:
                raise TableError(f"chord for {piece!r} must be an int in 1..{N_CHORDS}")
            if chord in by_chord:
                raise TableError(f"chord {chord} is used by {by_chord[chord]!r} and {piece!r}")
            by_chord[chord] = piece
        missing: list[str] = [ch for ch in ALPHABET if ch not in entries]
        if missing:
            raise TableError(f"no single-symbol entry for {''.join(missing)!r}")
        self._by_chord: dict[int, str] = dict(sorted(by_chord.items()))
        self._by_piece: dict[str, int] = {p: c for c, p in self._by_chord.items()}
        self._max_len: int = max(len(p) for p in self._by_piece)

    @property
    def entries(self) -> dict[str, int]:
        return dict(self._by_piece)

    def chord(self, piece: str) -> int:
        return self._by_piece[piece]

    def piece(self, chord: int) -> str:
        return self._by_chord[chord]

    def max_len(self) -> int:
        return self._max_len

    def to_json(self) -> str:
        rows: list[dict[str, Any]] = [{"piece": p, "chord": c} for p, c in self._by_piece.items()]
        data: dict[str, Any] = {"format": FORMAT, "version": VERSION, "entries": rows}
        return json.dumps(data, ensure_ascii=False, indent=2) + "\n"

    @classmethod
    def from_json(cls, data: str) -> Table:
        try:
            obj: Any = json.loads(data)
            if not isinstance(obj, dict) or obj.get("format") != FORMAT or obj.get("version") != VERSION:
                raise TableError("not a steno-zero table, version 1")
            rows: Any = obj["entries"]
            entries: dict[str, int] = {}
            row: Any
            for row in rows:
                piece: Any = row["piece"]
                if piece in entries:
                    raise TableError(f"piece {piece!r} repeated")
                entries[piece] = row["chord"]
            return cls(entries)
        except TableError:
            raise
        except (ValueError, KeyError, TypeError) as exc:
            raise TableError(f"bad table JSON: {exc}") from exc

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Table):
            return NotImplemented
        return self._by_piece == other._by_piece

    def __hash__(self) -> int:
        return hash(tuple(self._by_chord.items()))

    def __len__(self) -> int:
        return len(self._by_piece)

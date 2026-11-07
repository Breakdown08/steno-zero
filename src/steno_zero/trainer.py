"""Browser trainer: data export, exam logs and statistics."""

import hashlib
import json
import re
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any

from steno_zero.alphabet import ALPHABET, normalize
from steno_zero.chords import N_CHORDS, N_KEYS, chord_costs, chord_keys, neighbours
from steno_zero.corpus import split_corpus
from steno_zero.params import CostParams
from steno_zero.simulate import segment
from steno_zero.table import Table

KEY_CODES: tuple[str, ...] = (
    "KeyA",
    "KeyS",
    "KeyD",
    "KeyF",
    "KeyV",
    "KeyN",
    "KeyJ",
    "KeyK",
    "KeyL",
    "Semicolon",
)
KEY_LABELS: tuple[str, ...] = ("a", "s", "d", "f", "v", "n", "j", "k", "l", ";")
HELP_KEY: str = "Slash"
DATA_FORMAT: str = "steno-zero/trainer-data"
LOG_FORMAT: str = "steno-zero/trainer-log"
VERSION: int = 1
DATA_PREFIX: str = "window.STENO_ZERO_DATA = "
DATA_SUFFIX: str = ";\n"
PHRASE_MIN_LEN: int = 10
PHRASE_MAX_LEN: int = 60
HOME_LIMIT: int = 200
EXAM_LIMIT: int = 100
EXAM_SIZE: int = 5


class TrainerLogError(ValueError): ...


def chord_label(chord: int) -> str:
    return " ".join(KEY_LABELS[i] for i in chord_keys(chord))


def help_order(table: Table) -> list[tuple[str, int]]:
    entries: dict[str, int] = table.entries
    pieces: list[str] = sorted(
        entries, key=lambda piece: (len(piece), tuple(ALPHABET.index(ch) for ch in piece))
    )
    return [(piece, entries[piece]) for piece in pieces]


def pick_phrases(text: str, min_len: int, max_len: int, limit: int) -> list[str]:
    if min_len < 1 or max_len < min_len or limit < 1:
        raise ValueError("need 1 <= min_len <= max_len and limit >= 1")
    cuts: list[int] = [m.end() for m in re.finditer(r"[.!?](?=\s)", text)]
    found: dict[str, None] = {}
    i: int
    for i in range(len(cuts) - 1):
        sentence: str = text[cuts[i] : cuts[i + 1]].strip().strip(" -")
        if min_len <= len(sentence) <= max_len:
            found[sentence] = None
    candidates: list[str] = list(found)
    if len(candidates) <= limit:
        return candidates
    return [candidates[k * len(candidates) // limit] for k in range(limit)]


def split_phrases(
    text: str, min_len: int, max_len: int, home_limit: int, exam_limit: int
) -> tuple[list[str], list[str]]:
    train: str
    test: str
    train, test = split_corpus(text, 0.1)
    exam: list[str] = pick_phrases(test, min_len, max_len, exam_limit)
    home: list[str] = [p for p in pick_phrases(train, min_len, max_len, home_limit) if p not in exam]
    if not home:
        raise ValueError("no home phrases")
    if not exam:
        raise ValueError("no exam phrases")
    return home, exam


def table_sha256(table: Table) -> str:
    return hashlib.sha256(table.to_json().encode("utf-8")).hexdigest()


def trainer_data(
    tables: Sequence[tuple[str, Table]],
    phrases: Sequence[str],
    exam_phrases: Sequence[str],
    exam_size: int,
) -> dict[str, Any]:
    if not tables:
        raise ValueError("no tables")
    names: list[str] = [name for name, _ in tables]
    name: str
    for name in names:
        if re.fullmatch(r"[a-z0-9-]+", name) is None:
            raise ValueError(f"bad table name {name!r}")
    if len(set(names)) != len(names):
        raise ValueError("table names repeat")
    if not phrases or not exam_phrases:
        raise ValueError("phrase sets must not be empty")
    phrase: str
    for phrase in [*phrases, *exam_phrases]:
        if phrase == "" or normalize(phrase) != phrase:
            raise ValueError(f"phrase {phrase!r} is empty or not normalised")
    if len(set(phrases)) != len(phrases) or len(set(exam_phrases)) != len(exam_phrases):
        raise ValueError("phrases repeat")
    if not set(phrases).isdisjoint(exam_phrases):
        raise ValueError("home and exam phrases overlap")
    if exam_size < 1:
        raise ValueError("exam_size must be at least 1")
    costs: tuple[int, ...] = chord_costs(CostParams())
    out: list[dict[str, Any]] = []
    table: Table
    for name, table in tables:
        out.append(
            {
                "name": name,
                "sha256": table_sha256(table),
                "entries": [[p, c, chord_label(c)] for p, c in help_order(table)],
                "segments": _segments(phrases, table, costs),
                "exam_segments": _segments(exam_phrases, table, costs),
            }
        )
    return {
        "format": DATA_FORMAT,
        "version": VERSION,
        "keys": [{"code": c, "label": lbl} for c, lbl in zip(KEY_CODES, KEY_LABELS, strict=True)],
        "help_key": HELP_KEY,
        "exam_size": exam_size,
        "phrases": list(phrases),
        "exam_phrases": list(exam_phrases),
        "tables": out,
    }


def _segments(phrases: Sequence[str], table: Table, costs: Sequence[int]) -> list[list[list[Any]]]:
    return [[[table.piece(c), c] for c in segment(p, table, costs).chords] for p in phrases]


def data_js(data: Mapping[str, Any]) -> str:
    return DATA_PREFIX + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + DATA_SUFFIX


def write_data_js(data: Mapping[str, Any], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    f: IO[str]
    with out.open("w", encoding="utf-8", newline="\n") as f:
        f.write(data_js(data))


def read_data_js(path: Path) -> dict[str, Any]:
    text: str = path.read_text(encoding="utf-8")
    if not (text.startswith(DATA_PREFIX) and text.endswith(DATA_SUFFIX)):
        raise ValueError("not a trainer data.js")
    try:
        obj: Any = json.loads(text[len(DATA_PREFIX) : len(text) - len(DATA_SUFFIX)])
    except ValueError as exc:
        raise ValueError(f"bad data.js JSON: {exc}") from exc
    if not isinstance(obj, dict) or obj.get("format") != DATA_FORMAT or obj.get("version") != VERSION:
        raise ValueError("not a steno-zero trainer data, version 1")
    return obj


@dataclass(frozen=True)
class Attempt:
    phrase: int
    pos: int
    target: int
    typed: int
    down_ms: float
    up_ms: float


@dataclass(frozen=True)
class TrainerLog:
    session: str
    table: str
    table_sha256: str
    started: str
    finished: str
    user_agent: str
    max_held: int
    phrases: tuple[int, ...]
    chars: int
    attempts: tuple[Attempt, ...]


def _int(value: object, name: str, low: int, high: int | None) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < low
        or (high is not None and value > high)
    ):
        raise TrainerLogError(f"{name} must be an int >= {low}" + ("" if high is None else f" and <= {high}"))
    return value


def _attempt(raw: object) -> Attempt:
    if not isinstance(raw, dict):
        raise TrainerLogError("attempt must be an object")
    name: str
    for name in ("phrase", "pos", "target", "typed", "down_ms", "up_ms"):
        if name not in raw:
            raise TrainerLogError(f"attempt has no {name}")
    times: list[float] = []
    for name in ("down_ms", "up_ms"):
        t: object = raw[name]
        if not isinstance(t, int | float) or isinstance(t, bool):
            raise TrainerLogError(f"{name} must be a number")
        times.append(t)
    if not 0 <= times[0] <= times[1]:
        raise TrainerLogError("need 0 <= down_ms <= up_ms")
    return Attempt(
        _int(raw["phrase"], "phrase", 0, None),
        _int(raw["pos"], "pos", 0, None),
        _int(raw["target"], "target", 1, N_CHORDS),
        _int(raw["typed"], "typed", 1, N_CHORDS),
        times[0],
        times[1],
    )


def read_trainer_log(text: str) -> TrainerLog:
    try:
        obj: Any = json.loads(text)
    except ValueError as exc:
        raise TrainerLogError(f"bad JSON: {exc}") from exc
    if not isinstance(obj, dict):
        raise TrainerLogError("log must be an object")
    if obj.get("format") != LOG_FORMAT or obj.get("version") != VERSION:
        raise TrainerLogError("not a steno-zero trainer log, version 1")
    strings: dict[str, str] = {}
    key: str
    for key in ("session", "table", "table_sha256", "started", "finished", "user_agent"):
        value: Any = obj.get(key)
        if not isinstance(value, str):
            raise TrainerLogError(f"{key} must be a string")
        strings[key] = value
    if strings["session"] == "":
        raise TrainerLogError("session must not be empty")
    max_held: int = _int(obj.get("max_held"), "max_held", 0, N_KEYS)
    chars: int = _int(obj.get("chars"), "chars", 1, None)
    raw_phrases: Any = obj.get("phrases")
    if not isinstance(raw_phrases, list) or not raw_phrases:
        raise TrainerLogError("phrases must be a non-empty list")
    phrases: tuple[int, ...] = tuple(_int(v, "phrases item", 0, None) for v in raw_phrases)
    raw_attempts: Any = obj.get("attempts")
    if not isinstance(raw_attempts, list) or not raw_attempts:
        raise TrainerLogError("attempts must be a non-empty list")
    attempts: list[Attempt] = []
    raw: Any
    for raw in raw_attempts:
        attempt: Attempt = _attempt(raw)
        if attempt.phrase not in phrases:
            raise TrainerLogError(f"attempt phrase {attempt.phrase} is not in phrases")
        if attempts and attempt.up_ms < attempts[-1].up_ms:
            raise TrainerLogError("up_ms must not decrease")
        attempts.append(attempt)
    if attempts[-1].up_ms <= attempts[0].down_ms:
        raise TrainerLogError("session time must be positive")
    return TrainerLog(
        session=strings["session"],
        table=strings["table"],
        table_sha256=strings["table_sha256"],
        started=strings["started"],
        finished=strings["finished"],
        user_agent=strings["user_agent"],
        max_held=max_held,
        phrases=phrases,
        chars=chars,
        attempts=tuple(attempts),
    )


@dataclass(frozen=True)
class SessionStats:
    session: str
    table: str
    started: str
    phrases: int
    chars: int
    time_s: float
    chars_per_min: float
    attempts: int
    misses: int
    miss_rate: float


@dataclass(frozen=True)
class ChordStats:
    chord: int
    label: str
    attempts: int
    correct: int
    intervals: int
    median_ms: float | None
    typed: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class TrainerStats:
    sessions: tuple[SessionStats, ...]
    attempts: int
    correct: int
    neighbour_misses: int
    other_misses: int
    slip_prob: float
    median_ms: float | None
    chords: tuple[ChordStats, ...]


def trainer_stats(logs: Sequence[TrainerLog]) -> TrainerStats:
    if not logs:
        raise ValueError("no logs")
    sessions: list[str] = [log.session for log in logs]
    if len(set(sessions)) != len(sessions):
        raise ValueError("two logs have the same session")
    stats: list[SessionStats] = []
    attempts: int = 0
    correct: int = 0
    near: int = 0
    slots: int = 0
    intervals: list[float] = []
    per_attempts: dict[int, int] = {}
    per_correct: dict[int, int] = {}
    per_intervals: dict[int, list[float]] = {}
    per_typed: dict[int, dict[int, int]] = {}
    log: TrainerLog
    for log in logs:
        misses: int = 0
        previous: Attempt | None = None
        a: Attempt
        for a in log.attempts:
            t: int = a.target
            attempts += 1
            per_attempts[t] = per_attempts.get(t, 0) + 1
            per_intervals.setdefault(t, [])
            per_typed.setdefault(t, {})
            slots += len(neighbours(t))
            ok: bool = a.typed == t
            if ok:
                correct += 1
                per_correct[t] = per_correct.get(t, 0) + 1
            else:
                misses += 1
                per_typed[t][a.typed] = per_typed[t].get(a.typed, 0) + 1
                if a.typed in neighbours(t):
                    near += 1
            if (
                ok
                and previous is not None
                and previous.typed == previous.target
                and previous.phrase == a.phrase
                and previous.pos == a.pos - 1
            ):
                gap: float = a.up_ms - previous.up_ms
                intervals.append(gap)
                per_intervals[t].append(gap)
            previous = a
        time_s: float = (log.attempts[-1].up_ms - log.attempts[0].down_ms) / 1000
        stats.append(
            SessionStats(
                log.session,
                log.table,
                log.started,
                len(log.phrases),
                log.chars,
                time_s,
                log.chars / time_s * 60,
                len(log.attempts),
                misses,
                misses / len(log.attempts),
            )
        )
    chords: list[ChordStats] = []
    chord: int
    for chord in sorted(per_attempts):
        gaps: list[float] = per_intervals[chord]
        chords.append(
            ChordStats(
                chord,
                chord_label(chord),
                per_attempts[chord],
                per_correct.get(chord, 0),
                len(gaps),
                float(statistics.median(gaps)) if gaps else None,
                tuple(sorted(per_typed[chord].items())),
            )
        )
    return TrainerStats(
        sessions=tuple(sorted(stats, key=lambda s: (s.started, s.session))),
        attempts=attempts,
        correct=correct,
        neighbour_misses=near,
        other_misses=attempts - correct - near,
        slip_prob=near / slots,
        median_ms=float(statistics.median(intervals)) if intervals else None,
        chords=tuple(chords),
    )

"""Keyboard calibration log and keyboard profile: which chords the keyboard swallows."""

import hashlib
import itertools
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from steno_zero.chords import N_CHORDS, N_KEYS, allowed_chords
from steno_zero.trainer import chord_label

CALIBRATION_FORMAT: str = "steno-zero/keyboard-calibration"
PROFILE_FORMAT: str = "steno-zero/keyboard-profile"
KEYBOARD_VERSION: int = 1
CALIBRATION_ATTEMPTS: int = 3
KEYBOARDS_DIR: Path = Path("data/keyboards")
NAME_PATTERN: str = "[a-z0-9-]+"


class KeyboardError(ValueError): ...


def calibration_chords() -> tuple[int, ...]:
    out: list[int] = []
    size: int
    for size in (2, 3):
        out += sorted(sum(1 << k for k in keys) for keys in itertools.combinations(range(N_KEYS), size))
    return tuple(out)


@dataclass(frozen=True)
class CalibrationAttempt:
    target: int
    typed: int
    down_ms: float
    up_ms: float


@dataclass(frozen=True)
class CalibrationLog:
    session: str
    started: str
    finished: str
    user_agent: str
    max_held: int
    attempts: tuple[CalibrationAttempt, ...]


@dataclass(frozen=True)
class Blocked:
    chord: int
    unclear: bool


@dataclass(frozen=True)
class KeyboardProfile:
    name: str
    session: str
    created: str
    blocked: tuple[Blocked, ...]


def _int(value: object, name: str, low: int, high: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
        raise KeyboardError(f"{name} must be an int in {low}..{high}")
    return value


def _string(obj: dict[str, Any], key: str) -> str:
    value: Any = obj.get(key)
    if not isinstance(value, str):
        raise KeyboardError(f"{key} must be a string")
    return value


def _load(text: str, fmt: str) -> dict[str, Any]:
    try:
        obj: Any = json.loads(text)
    except ValueError as exc:
        raise KeyboardError(f"bad JSON: {exc}") from exc
    if not isinstance(obj, dict):
        raise KeyboardError("must be a JSON object")
    version: Any = obj.get("version")
    if obj.get("format") != fmt or isinstance(version, bool) or version != KEYBOARD_VERSION:
        raise KeyboardError(f"not a {fmt} file, version {KEYBOARD_VERSION}")
    return obj


def _attempt(raw: object, allowed: frozenset[int]) -> CalibrationAttempt:
    if not isinstance(raw, dict):
        raise KeyboardError("attempt must be an object")
    name: str
    for name in ("target", "typed", "down_ms", "up_ms"):
        if name not in raw:
            raise KeyboardError(f"attempt has no {name}")
    target: Any = raw["target"]
    if not isinstance(target, int) or isinstance(target, bool) or target not in allowed:
        raise KeyboardError(f"target is not a calibration chord: {target!r}")
    typed: int = _int(raw["typed"], "typed", 1, N_CHORDS)
    times: list[float] = []
    for name in ("down_ms", "up_ms"):
        t: Any = raw[name]
        if not isinstance(t, int | float) or isinstance(t, bool):
            raise KeyboardError(f"{name} must be a number")
        times.append(t)
    if not 0 <= times[0] <= times[1]:
        raise KeyboardError("need 0 <= down_ms <= up_ms")
    return CalibrationAttempt(target, typed, times[0], times[1])


def read_calibration_log(text: str) -> CalibrationLog:
    obj: dict[str, Any] = _load(text, CALIBRATION_FORMAT)
    session: str = _string(obj, "session")
    if session == "":
        raise KeyboardError("session must not be empty")
    started: str = _string(obj, "started")
    finished: str = _string(obj, "finished")
    user_agent: str = _string(obj, "user_agent")
    max_held: int = _int(obj.get("max_held"), "max_held", 0, N_KEYS)
    raw_attempts: Any = obj.get("attempts")
    if not isinstance(raw_attempts, list) or not raw_attempts:
        raise KeyboardError("attempts must be a non-empty list")
    allowed: frozenset[int] = frozenset(calibration_chords())
    return CalibrationLog(
        session, started, finished, user_agent, max_held, tuple(_attempt(a, allowed) for a in raw_attempts)
    )


def _check_name(name: str) -> None:
    if re.fullmatch(NAME_PATTERN, name) is None:
        raise KeyboardError(f"name must match {NAME_PATTERN}: {name!r}")


def build_profile(log: CalibrationLog, name: str) -> KeyboardProfile:
    _check_name(name)
    by_chord: dict[int, list[int]] = {c: [] for c in calibration_chords()}
    attempt: CalibrationAttempt
    for attempt in log.attempts:
        by_chord[attempt.target].append(attempt.typed)
    missing: list[int] = []
    blocked: dict[int, bool] = {}
    chord: int
    typed: list[int]
    for chord, typed in by_chord.items():
        if chord in typed:
            continue
        if len(typed) < CALIBRATION_ATTEMPTS:
            missing.append(chord)
            continue
        blocked[chord] = any(t & chord != t for t in typed)
    if missing:
        listed: str = ", ".join(chord_label(c) for c in missing)
        raise KeyboardError(f"calibration incomplete: {listed}")
    minimal: list[Blocked] = [
        Blocked(c, unclear)
        for c, unclear in sorted(blocked.items())
        if not any(b != c and c & b == b for b in blocked)
    ]
    return KeyboardProfile(name, log.session, log.started, tuple(minimal))


def profile_json(profile: KeyboardProfile) -> str:
    obj: dict[str, Any] = {
        "format": PROFILE_FORMAT,
        "version": KEYBOARD_VERSION,
        "name": profile.name,
        "session": profile.session,
        "created": profile.created,
        "blocked": [
            {"chord": b.chord, "label": chord_label(b.chord), "unclear": b.unclear} for b in profile.blocked
        ],
    }
    return json.dumps(obj, ensure_ascii=False, indent=1) + "\n"


def read_profile(text: str) -> KeyboardProfile:
    obj: dict[str, Any] = _load(text, PROFILE_FORMAT)
    name: str = _string(obj, "name")
    _check_name(name)
    session: str = _string(obj, "session")
    created: str = _string(obj, "created")
    raw_blocked: Any = obj.get("blocked")
    if not isinstance(raw_blocked, list):
        raise KeyboardError("blocked must be a list")
    blocked: list[Blocked] = []
    raw: Any
    for raw in raw_blocked:
        if not isinstance(raw, dict) or not all(k in raw for k in ("chord", "label", "unclear")):
            raise KeyboardError("blocked item needs chord, label and unclear")
        chord: int = _int(raw["chord"], "chord", 1, N_CHORDS)
        if chord.bit_count() < 2:
            raise KeyboardError(f"blocked chord must have at least 2 keys: {chord}")
        if raw["label"] != chord_label(chord):
            raise KeyboardError(f"wrong label for chord {chord}: {raw['label']!r}")
        if not isinstance(raw["unclear"], bool):
            raise KeyboardError("unclear must be a bool")
        if blocked and chord <= blocked[-1].chord:
            raise KeyboardError("blocked must be strictly ascending")
        blocked.append(Blocked(chord, raw["unclear"]))
    a: Blocked
    for a in blocked:
        if any(b is not a and a.chord & b.chord == b.chord for b in blocked):
            raise KeyboardError(f"blocked chord {a.chord} contains another blocked chord")
    return KeyboardProfile(name, session, created, tuple(blocked))


def profile_sha256(profile: KeyboardProfile) -> str:
    return hashlib.sha256(profile_json(profile).encode("utf-8")).hexdigest()


def is_available(chord: int, profile: KeyboardProfile | None) -> bool:
    if not 1 <= chord <= N_CHORDS:
        raise ValueError(f"chord out of range 1..{N_CHORDS}: {chord}")
    if profile is None:
        return True
    return not any(chord & b.chord == b.chord for b in profile.blocked)


def available_chords(max_keys: int, profile: KeyboardProfile | None) -> tuple[int, ...]:
    return tuple(c for c in allowed_chords(max_keys) if is_available(c, profile))

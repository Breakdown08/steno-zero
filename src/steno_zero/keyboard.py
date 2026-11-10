"""Keyboard calibration log and keyboard profile: which key combinations the keyboard swallows."""

import hashlib
import itertools
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from steno_zero.chords import FINGERS, N_CHORDS, N_KEYS, allowed_chords, chord_keys
from steno_zero.layout import CODE_PATTERN, NAME_PATTERN, Layout, LayoutError, layout_from_obj

CALIBRATION_FORMAT: str = "steno-zero/keyboard-calibration"
PROFILE_FORMAT: str = "steno-zero/keyboard-profile"
KEYBOARD_VERSION: int = 2
CALIBRATION_ATTEMPTS: int = 3
KEYBOARDS_DIR: Path = Path("data/keyboards")


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
    layout: Layout
    attempts: tuple[CalibrationAttempt, ...]


@dataclass(frozen=True)
class Blocked:
    keys: tuple[str, ...]
    unclear: bool


@dataclass(frozen=True)
class KeyboardProfile:
    name: str
    session: str
    created: str
    keys: tuple[str, ...]
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
    if obj.get("format") != fmt:
        raise KeyboardError(f"not a {fmt} file, version {KEYBOARD_VERSION}")
    if version == 1 and not isinstance(version, bool):
        raise KeyboardError(f"{fmt} version 1 is no longer read")
    if isinstance(version, bool) or version != KEYBOARD_VERSION:
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
    try:
        layout: Layout = layout_from_obj(obj.get("layout"))
    except LayoutError as exc:
        raise KeyboardError(f"layout: {exc}") from exc
    raw_attempts: Any = obj.get("attempts")
    if not isinstance(raw_attempts, list) or not raw_attempts:
        raise KeyboardError("attempts must be a non-empty list")
    allowed: frozenset[int] = frozenset(calibration_chords())
    return CalibrationLog(
        session,
        started,
        finished,
        user_agent,
        max_held,
        layout,
        tuple(_attempt(a, allowed) for a in raw_attempts),
    )


def _check_name(name: str) -> None:
    if re.fullmatch(NAME_PATTERN, name) is None:
        raise KeyboardError(f"name must match {NAME_PATTERN}: {name!r}")


def _chord_text(chord: int) -> str:
    return " ".join(FINGERS[i] for i in chord_keys(chord))


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
        listed: str = ", ".join(_chord_text(c) for c in missing)
        raise KeyboardError(f"calibration incomplete: {listed}")
    minimal: list[Blocked] = [
        Blocked(tuple(sorted(log.layout.codes[i] for i in chord_keys(c))), unclear)
        for c, unclear in blocked.items()
        if not any(b != c and c & b == b for b in blocked)
    ]
    minimal.sort(key=lambda b: (len(b.keys), b.keys))
    return KeyboardProfile(name, log.session, log.started, tuple(sorted(log.layout.codes)), tuple(minimal))


def profile_json(profile: KeyboardProfile) -> str:
    obj: dict[str, Any] = {
        "format": PROFILE_FORMAT,
        "version": KEYBOARD_VERSION,
        "name": profile.name,
        "session": profile.session,
        "created": profile.created,
        "keys": list(profile.keys),
        "blocked": [{"keys": list(b.keys), "unclear": b.unclear} for b in profile.blocked],
    }
    return json.dumps(obj, ensure_ascii=False, indent=1) + "\n"


def _codes(raw: object, what: str, minimum: int) -> tuple[str, ...]:
    if not isinstance(raw, list) or len(raw) < minimum:
        raise KeyboardError(f"{what} must be a list of at least {minimum} key codes")
    code: Any
    for code in raw:
        if not isinstance(code, str) or re.fullmatch(CODE_PATTERN, code) is None:
            raise KeyboardError(f"{what}: bad key code {code!r}")
    if any(a >= b for a, b in itertools.pairwise(raw)):
        raise KeyboardError(f"{what} must be strictly ascending")
    return tuple(raw)


def read_profile(text: str) -> KeyboardProfile:
    obj: dict[str, Any] = _load(text, PROFILE_FORMAT)
    name: str = _string(obj, "name")
    _check_name(name)
    session: str = _string(obj, "session")
    created: str = _string(obj, "created")
    keys: tuple[str, ...] = _codes(obj.get("keys"), "keys", 2)
    raw_blocked: Any = obj.get("blocked")
    if not isinstance(raw_blocked, list):
        raise KeyboardError("blocked must be a list")
    blocked: list[Blocked] = []
    raw: Any
    for raw in raw_blocked:
        if not isinstance(raw, dict) or not all(k in raw for k in ("keys", "unclear")):
            raise KeyboardError("blocked item needs keys and unclear")
        combo: tuple[str, ...] = _codes(raw["keys"], "blocked keys", 2)
        outside: list[str] = [k for k in combo if k not in keys]
        if outside:
            raise KeyboardError(f"blocked keys are not in keys: {', '.join(outside)}")
        if not isinstance(raw["unclear"], bool):
            raise KeyboardError("unclear must be a bool")
        item: Blocked = Blocked(combo, raw["unclear"])
        if blocked and (len(item.keys), item.keys) <= (len(blocked[-1].keys), blocked[-1].keys):
            raise KeyboardError("blocked must be strictly ascending by (length, keys)")
        blocked.append(item)
    a: Blocked
    for a in blocked:
        if any(b is not a and set(b.keys) <= set(a.keys) for b in blocked):
            raise KeyboardError(f"blocked {keys_label(a.keys)} contains another blocked combination")
    return KeyboardProfile(name, session, created, keys, tuple(blocked))


def profile_sha256(profile: KeyboardProfile) -> str:
    return hashlib.sha256(profile_json(profile).encode("utf-8")).hexdigest()


def finger_blocked(profile: KeyboardProfile, layout: Layout) -> tuple[int, ...]:
    uncovered: list[str] = [c for c in layout.codes if c not in profile.keys]
    if uncovered:
        raise KeyboardError(
            f"profile {profile.name} does not cover layout {layout.name}; not calibrated: "
            + ", ".join(uncovered)
        )
    return tuple(
        sorted(
            sum(1 << layout.codes.index(k) for k in b.keys)
            for b in profile.blocked
            if all(k in layout.codes for k in b.keys)
        )
    )


def is_available(chord: int, blocked: Sequence[int]) -> bool:
    if not 1 <= chord <= N_CHORDS:
        raise ValueError(f"chord out of range 1..{N_CHORDS}: {chord}")
    return not any(chord & b == b for b in blocked)


def available_chords(max_keys: int, blocked: Sequence[int]) -> tuple[int, ...]:
    return tuple(c for c in allowed_chords(max_keys) if is_available(c, blocked))


def keys_label(keys: Sequence[str]) -> str:
    return "+".join(keys)

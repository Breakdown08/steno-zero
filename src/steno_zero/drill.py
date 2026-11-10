"""Random-chord drill: the plan built in Python, played by the page, and the log the page writes."""

import json
import random
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any

from steno_zero.chords import N_CHORDS
from steno_zero.keyboard import available_chords, calibration_chords
from steno_zero.layout import NAME_PATTERN, Layout, LayoutError, layout_from_obj

DRILL_PLAN_FORMAT: str = "steno-zero/drill-plan"
DRILL_LOG_FORMAT: str = "steno-zero/drill-log"
DRILL_VERSION: int = 2
DRILL_PREFIX: str = "window.STENO_ZERO_DRILL = "
DRILL_SUFFIX: str = ";\n"
DRILL_SEED: int = 0
DRILL_BLOCKS: int = 100
DRILL_SIZE: int = 100
MAX_SIZE: int = 1000
LEFT_MASK: int = 31  # keys 0..4 are the left hand

type Stratum = tuple[int, int]


class DrillLogError(ValueError): ...


def drill_strata(max_keys: int, blocked: Sequence[int] = ()) -> dict[tuple[int, int], tuple[int, ...]]:
    groups: dict[Stratum, list[int]] = {}
    chord: int
    for chord in available_chords(max_keys, blocked):
        groups.setdefault((chord.bit_count(), (chord & LEFT_MASK).bit_count()), []).append(chord)
    return {key: tuple(groups[key]) for key in sorted(groups)}


def _split(total: int, parts: int, rng: random.Random) -> list[int]:
    """`total` over `parts` places, counts differ by at most 1, the extra ones go to random places."""
    counts: list[int] = [total // parts] * parts
    extra: int
    for extra in rng.sample(range(parts), total % parts):
        counts[extra] += 1
    return counts


def _arrange(chords: list[int], rng: random.Random) -> list[int]:
    """A random order of the chords with no two equal ones in a row."""
    left: dict[int, int] = {}
    chord: int
    for chord in chords:
        left[chord] = left.get(chord, 0) + 1
    out: list[int] = []
    prev: int | None = None
    while len(out) < len(chords):
        remaining: int = len(chords) - len(out)
        options: list[int] = sorted(c for c in left if c != prev)
        if not options:
            raise ValueError("cannot avoid a repeated chord in a row")
        forced: list[int] = [c for c in options if left[c] * 2 > remaining]
        pick: int = forced[0] if forced else rng.choices(options, weights=[left[c] for c in options])[0]
        out.append(pick)
        left[pick] -= 1
        if left[pick] == 0:
            del left[pick]
        prev = pick
    return out


def _draw(deck: list[int], chords: tuple[int, ...], rng: random.Random) -> int:
    """The next chord of a stratum from its shuffled deck; the deck is shuffled again when it is empty."""
    if not deck:
        deck.extend(chords)
        rng.shuffle(deck)
    return deck.pop()


def _block(
    size: int,
    ns: list[int],
    strata: dict[Stratum, tuple[int, ...]],
    decks: dict[Stratum, list[int]],
    rng: random.Random,
) -> tuple[int, ...]:
    drawn: list[int] = []
    n_count: int
    n: int
    for n, n_count in zip(ns, _split(size, len(ns), rng), strict=True):
        keys: list[Stratum] = [key for key in strata if key[0] == n]
        key_count: int
        key: Stratum
        for key, key_count in zip(keys, _split(n_count, len(keys), rng), strict=True):
            drawn += [_draw(decks[key], strata[key], rng) for _ in range(key_count)]
    return tuple(_arrange(drawn, rng))


def drill_plan(
    seed: int, blocks: int, size: int, max_keys: int, blocked: Sequence[int] = ()
) -> tuple[tuple[int, ...], ...]:
    strata: dict[Stratum, tuple[int, ...]] = drill_strata(max_keys, blocked)
    ns: list[int] = sorted({n for n, _ in strata})
    if blocks < 1:
        raise ValueError("blocks must be at least 1")
    if size < len(ns):
        raise ValueError(f"size must be at least {len(ns)} (one chord per number of keys)")
    if size > MAX_SIZE:
        raise ValueError(f"size must be at most {MAX_SIZE}")
    rng: random.Random = random.Random(seed)
    decks: dict[Stratum, list[int]] = {key: [] for key in strata}
    return tuple(_block(size, ns, strata, decks, rng) for _ in range(blocks))


def drill_data(seed: int, blocks: int, size: int, max_keys: int) -> dict[str, Any]:
    plan: tuple[tuple[int, ...], ...] = drill_plan(seed, blocks, size, max_keys)
    return {
        "format": DRILL_PLAN_FORMAT,
        "version": DRILL_VERSION,
        "seed": seed,
        "max_keys": max_keys,
        "size": size,
        "calibration": list(calibration_chords()),
        "blocks": [list(b) for b in plan],
    }


def drill_js(data: Mapping[str, Any]) -> str:
    return DRILL_PREFIX + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + DRILL_SUFFIX


def write_drill_js(data: Mapping[str, Any], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    f: IO[str]
    with out.open("w", encoding="utf-8", newline="\n") as f:
        f.write(drill_js(data))


def read_drill_js(path: Path) -> dict[str, Any]:
    text: str = path.read_text(encoding="utf-8")
    if not (text.startswith(DRILL_PREFIX) and text.endswith(DRILL_SUFFIX)):
        raise ValueError("not a drill.js")
    try:
        obj: Any = json.loads(text[len(DRILL_PREFIX) : len(text) - len(DRILL_SUFFIX)])
    except ValueError as exc:
        raise ValueError(f"bad drill.js JSON: {exc}") from exc
    if isinstance(obj, dict) and obj.get("format") == DRILL_PLAN_FORMAT and obj.get("version") == 1:
        raise ValueError("drill plan version 1 is no longer read")
    if (
        not isinstance(obj, dict)
        or obj.get("format") != DRILL_PLAN_FORMAT
        or obj.get("version") != DRILL_VERSION
    ):
        raise ValueError(f"not a steno-zero drill plan, version {DRILL_VERSION}")
    return obj


@dataclass(frozen=True)
class Presentation:
    i: int
    target: int
    typed: int
    shown_ms: float
    down_ms: float
    up_ms: float


@dataclass(frozen=True)
class DrillLog:
    session: str
    seed: int
    block: int
    max_keys: int
    layout: Layout
    keyboard: tuple[str, str] | None
    started: str
    finished: str
    user_agent: str
    max_held: int
    presentations: tuple[Presentation, ...]


def _int(value: object, name: str, low: int, high: int | None) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < low
        or (high is not None and value > high)
    ):
        raise DrillLogError(f"{name} must be an int >= {low}" + ("" if high is None else f" and <= {high}"))
    return value


def _number(value: object, name: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise DrillLogError(f"{name} must be a number")
    return value


def _presentation(raw: object, max_keys: int) -> Presentation:
    if not isinstance(raw, dict):
        raise DrillLogError("presentation must be an object")
    name: str
    for name in ("i", "target", "typed", "shown_ms", "down_ms", "up_ms"):
        if name not in raw:
            raise DrillLogError(f"presentation has no {name}")
    index: int = _int(raw["i"], "i", 0, None)
    target: int = _int(raw["target"], "target", 1, N_CHORDS)
    if target.bit_count() > max_keys:
        raise DrillLogError(f"target {target} has more than {max_keys} keys")
    typed: int = _int(raw["typed"], "typed", 1, N_CHORDS)
    shown: float = _number(raw["shown_ms"], "shown_ms")
    down: float = _number(raw["down_ms"], "down_ms")
    up: float = _number(raw["up_ms"], "up_ms")
    if not 0 <= shown <= down <= up:
        raise DrillLogError("need 0 <= shown_ms <= down_ms <= up_ms")
    return Presentation(index, target, typed, shown, down, up)


def _keyboard(raw: object) -> tuple[str, str] | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise DrillLogError("keyboard must be null or an object")
    name: Any = raw.get("name")
    sha: Any = raw.get("sha256")
    if not isinstance(name, str) or re.fullmatch(NAME_PATTERN, name) is None:
        raise DrillLogError(f"keyboard name must match {NAME_PATTERN}")
    if not isinstance(sha, str) or re.fullmatch("[0-9a-f]{64}", sha) is None:
        raise DrillLogError("keyboard sha256 must be 64 lowercase hex digits")
    return name, sha


def read_drill_log(text: str) -> DrillLog:
    try:
        obj: Any = json.loads(text)
    except ValueError as exc:
        raise DrillLogError(f"bad JSON: {exc}") from exc
    if not isinstance(obj, dict):
        raise DrillLogError("log must be an object")
    version: Any = obj.get("version")
    if obj.get("format") == DRILL_LOG_FORMAT and version == 1 and not isinstance(version, bool):
        raise DrillLogError("drill log version 1 is no longer read")
    if obj.get("format") != DRILL_LOG_FORMAT or isinstance(version, bool) or version != DRILL_VERSION:
        raise DrillLogError(f"not a steno-zero drill log, version {DRILL_VERSION}")
    strings: dict[str, str] = {}
    key: str
    for key in ("session", "started", "finished", "user_agent"):
        value: Any = obj.get(key)
        if not isinstance(value, str):
            raise DrillLogError(f"{key} must be a string")
        strings[key] = value
    if strings["session"] == "":
        raise DrillLogError("session must not be empty")
    seed: int = _int(obj.get("seed"), "seed", -(2**63), None)
    block: int = _int(obj.get("block"), "block", 0, None)
    max_keys: int = _int(obj.get("max_keys"), "max_keys", 2, 10)
    max_held: int = _int(obj.get("max_held"), "max_held", 0, 10)
    try:
        layout: Layout = layout_from_obj(obj.get("layout"))
    except LayoutError as exc:
        raise DrillLogError(f"layout: {exc}") from exc
    keyboard: tuple[str, str] | None = _keyboard(obj.get("keyboard"))
    raw_rows: Any = obj.get("presentations")
    if not isinstance(raw_rows, list) or not raw_rows:
        raise DrillLogError("presentations must be a non-empty list")
    rows: list[Presentation] = []
    raw: Any
    for raw in raw_rows:
        row: Presentation = _presentation(raw, max_keys)
        if rows and row.i <= rows[-1].i:
            raise DrillLogError(f"presentation i must increase: {row.i} after {rows[-1].i}")
        if rows and row.shown_ms < rows[-1].up_ms:
            raise DrillLogError(f"presentation {row.i} is shown before the previous one is released")
        rows.append(row)
    return DrillLog(
        session=strings["session"],
        seed=seed,
        block=block,
        max_keys=max_keys,
        layout=layout,
        keyboard=keyboard,
        started=strings["started"],
        finished=strings["finished"],
        user_agent=strings["user_agent"],
        max_held=max_held,
        presentations=tuple(rows),
    )

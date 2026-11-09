"""The synthetic measurements of the price checks: a known truth plus noise, built from a drill plan."""

import functools
import json
import random
from collections.abc import Callable
from pathlib import Path

import pandas as pd

from steno_zero.drill import DrillLog, Presentation, drill_plan
from steno_zero.keyboard import KeyboardProfile, profile_sha256
from steno_zero.price import PriceFit, fit_prices, presentations_frame
from tests.drill_helpers import Plan
from tests.keyboard_helpers import P1

FINGER: tuple[int, ...] = (0, 1, 2, 3, 3, 3, 3, 2, 1, 0)
type Keyboard = tuple[str, str] | None


def reference(chord: int) -> tuple[int, int, int]:
    """(keys, holes, both_hands), computed here from the definitions, not by the code under test."""
    holes: int = 0
    both: list[int] = []
    hand: range
    for hand in (range(0, 5), range(5, 10)):
        pressed: list[int] = [k for k in hand if chord >> k & 1]
        both.append(len(pressed))
        if pressed:
            fingers: set[int] = {FINGER[k] for k in pressed}
            holes += max(fingers) - min(fingers) + 1 - len(fingers)
    return chord.bit_count(), holes, int(both[0] > 0 and both[1] > 0)


def truth(chord: int) -> float:
    keys: int
    holes: int
    both: int
    keys, holes, both = reference(chord)
    return 400.0 + 100.0 * keys + 200.0 * holes + 150.0 * both


def times(shown: float, total: float) -> tuple[float, float, float]:
    return shown, shown + 0.6 * total, shown + total


def synth_logs(
    plan: Plan,
    keyboard: Keyboard = None,
    misses: bool = True,
    prefix: str = "s",
) -> list[DrillLog]:
    """Block b is the session f"{prefix}{b}"; a miss types target ^ 1 (target ^ 2 if that is 0)."""
    rng: random.Random = random.Random(0)
    logs: list[DrillLog] = []
    b: int
    block: tuple[int, ...]
    for b, block in enumerate(plan):
        rows: list[Presentation] = []
        shown: float = 1000.0
        i: int
        target: int
        for i, target in enumerate(block):
            total: float = max(100.0, truth(target) + rng.gauss(0.0, 50.0))
            holes: int = reference(target)[1]
            typed: int = target
            if misses and rng.random() < min(0.9, 0.02 + 0.15 * holes):
                typed = target ^ 1 or target ^ 2
            s: float
            d: float
            u: float
            s, d, u = times(shown, total)
            rows.append(Presentation(i, target, typed, s, d, u))
            shown = u + 50.0
        logs.append(
            DrillLog(
                f"{prefix}{b}",
                1,
                b,
                6,
                keyboard,
                f"2026-11-10T00:{b:02d}:00.000Z",
                "2026-11-10T01:00:00.000Z",
                "pytest",
                6,
                tuple(rows),
            )
        )
    return logs


def extra_log(rows: list[tuple[int, int]], keyboard: Keyboard = None, session: str = "extra") -> DrillLog:
    """A late session of (target, typed) pairs, timed by the same rule with a total of truth(target)."""
    presentations: list[Presentation] = []
    shown: float = 1000.0
    i: int
    target: int
    typed: int
    for i, (target, typed) in enumerate(rows):
        s: float
        d: float
        u: float
        s, d, u = times(shown, truth(target))
        presentations.append(Presentation(i, target, typed, s, d, u))
        shown = u + 50.0
    return DrillLog(
        session, 1, 99, 6, keyboard, "2026-11-11T00:00:00.000Z", "2026-11-11T01:00:00.000Z", "pytest", 6,
        tuple(presentations),
    )  # fmt: skip


def without(plan: Plan, drop: Callable[[int], bool]) -> Plan:
    return tuple(tuple(c for c in block if not drop(c)) for block in plan)


def keyboard_of(profile: KeyboardProfile | None) -> Keyboard:
    return None if profile is None else (profile.name, profile_sha256(profile))


@functools.cache
def main_plan() -> Plan:
    return drill_plan(1, 30, 100, 6)


@functools.cache
def p1_plan() -> Plan:
    return drill_plan(1, 30, 100, 6, P1)


@functools.cache
def main_logs() -> tuple[DrillLog, ...]:
    return tuple(synth_logs(main_plan()))


@functools.cache
def main_frame() -> pd.DataFrame:
    return presentations_frame(main_logs(), 5)


@functools.cache
def p1_logs() -> tuple[DrillLog, ...]:
    return tuple(synth_logs(p1_plan(), keyboard_of(P1)))


@functools.cache
def p1_frame() -> pd.DataFrame:
    return presentations_frame(p1_logs(), 5)


def fit(
    frame: pd.DataFrame,
    target: str = "total",
    model: str = "auto",
    max_keys: int = 6,
    folds: int = 5,
    seed: int = 0,
    max_ms: float = 5000.0,
    profile: KeyboardProfile | None = None,
) -> PriceFit:
    return fit_prices(frame, target, model, max_keys, folds, seed, max_ms, profile)


@functools.cache
def main_fit() -> PriceFit:
    return fit(main_frame())


@functools.cache
def p1_fit() -> PriceFit:
    return fit(p1_frame(), profile=P1)


def log_json(log: DrillLog) -> str:
    keyboard: dict[str, str] | None = (
        None if log.keyboard is None else {"name": log.keyboard[0], "sha256": log.keyboard[1]}
    )
    return json.dumps(
        {
            "format": "steno-zero/drill-log",
            "version": 1,
            "session": log.session,
            "seed": log.seed,
            "block": log.block,
            "max_keys": log.max_keys,
            "keyboard": keyboard,
            "started": log.started,
            "finished": log.finished,
            "user_agent": log.user_agent,
            "max_held": log.max_held,
            "presentations": [
                {
                    "i": p.i,
                    "target": p.target,
                    "typed": p.typed,
                    "shown_ms": p.shown_ms,
                    "down_ms": p.down_ms,
                    "up_ms": p.up_ms,
                }
                for p in log.presentations
            ],
        }
    )


def write_logs(logs: tuple[DrillLog, ...] | list[DrillLog], folder: Path) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    log: DrillLog
    for log in logs:
        path: Path = folder / f"{log.session}.json"
        path.write_text(log_json(log), encoding="utf-8")
        paths.append(path)
    return paths

"""Comparison of evolution with and without the surrogate filter. No torch."""

import dataclasses
import statistics
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from steno_zero.evolve import EvolveParams, EvolveResult, GenerationRecord, Screen, evolve
from steno_zero.params import PenaltyParams


@dataclass(frozen=True)
class RunStats:
    seed: int
    mode: str
    final_total: float
    exact_evaluations: int
    screened: int
    wall_s: float
    target: float
    generation_to_target: int | None
    evaluations_to_target: int | None
    seconds_to_target: float | None


def _run_one(
    text: str,
    costs: Sequence[int],
    penalty: PenaltyParams,
    horizon: float,
    params: EvolveParams,
    workers: int,
    screen: Screen | None,
    oversample: int,
) -> tuple[EvolveResult, float, dict[int, float]]:
    """One evolution: the result, the wall time, and the time of each generation's callback."""
    stamps: dict[int, float] = {}
    start: float = time.monotonic()

    def on_generation(rec: GenerationRecord) -> None:
        stamps[rec.generation] = time.monotonic() - start

    result: EvolveResult = evolve(
        text,
        costs,
        penalty,
        horizon,
        params,
        workers,
        on_generation,
        screen=screen,
        oversample=oversample,
    )
    return result, time.monotonic() - start, stamps


def _stats(
    seed: int,
    mode: str,
    result: EvolveResult,
    wall: float,
    stamps: dict[int, float],
    target: float,
    screened: int,
) -> RunStats:
    reached: GenerationRecord | None = next((r for r in result.history if r.best_total <= target), None)
    return RunStats(
        seed=seed,
        mode=mode,
        final_total=result.history[-1].best_total,
        exact_evaluations=result.history[-1].evaluations,
        screened=screened,
        wall_s=wall,
        target=target,
        generation_to_target=None if reached is None else reached.generation,
        evaluations_to_target=None if reached is None else reached.evaluations,
        seconds_to_target=None if reached is None else stamps[reached.generation],
    )


def compare_runs(
    text: str,
    costs: Sequence[int],
    penalty: PenaltyParams,
    horizon: float,
    params: EvolveParams,
    seeds: Sequence[int],
    oversample: int,
    screen: Screen,
    workers: int = 1,
) -> list[RunStats]:
    if oversample < 2:
        raise ValueError("oversample must be at least 2")
    if not seeds:
        raise ValueError("seeds must not be empty")
    runs: list[RunStats] = []
    seed: int
    for seed in seeds:
        own: EvolveParams = dataclasses.replace(params, seed=seed)
        base: EvolveResult
        wall: float
        stamps: dict[int, float]
        base, wall, stamps = _run_one(text, costs, penalty, horizon, own, workers, None, 1)
        target: float = base.history[-1].best_total
        runs.append(_stats(seed, "baseline", base, wall, stamps, target, 0))
        filtered: EvolveResult
        filtered, wall, stamps = _run_one(text, costs, penalty, horizon, own, workers, screen, oversample)
        screened: int = own.generations * oversample * (own.population - own.elite)
        runs.append(_stats(seed, "surrogate", filtered, wall, stamps, target, screened))
    return runs


def _ratio(base: float | None, sur: float | None) -> float | None:
    if base is None or sur is None or sur <= 0:
        return None
    return base / sur


def summarize(runs: Sequence[RunStats]) -> dict[str, Any]:
    seeds: list[int] = list(dict.fromkeys(r.seed for r in runs))
    pairs: list[tuple[RunStats, RunStats]] = []
    seed: int
    for seed in seeds:
        base: list[RunStats] = [r for r in runs if r.seed == seed and r.mode == "baseline"]
        sur: list[RunStats] = [r for r in runs if r.seed == seed and r.mode == "surrogate"]
        if len(base) != 1 or len(sur) != 1 or sum(1 for r in runs if r.seed == seed) != 2:
            raise ValueError(f"seed {seed} needs exactly one baseline and one surrogate run")
        pairs.append((base[0], sur[0]))
    if not pairs:
        raise ValueError("no runs")
    ev: list[float | None] = [_ratio(b.evaluations_to_target, s.evaluations_to_target) for b, s in pairs]
    tm: list[float | None] = [_ratio(b.seconds_to_target, s.seconds_to_target) for b, s in pairs]
    ev_ok: list[float] = [v for v in ev if v is not None]
    tm_ok: list[float] = [v for v in tm if v is not None]
    all_reached: bool = all(s.generation_to_target is not None for _, s in pairs)
    median_ev: float | None = statistics.median(ev_ok) if all_reached and len(ev_ok) == len(pairs) else None
    median_tm: float | None = statistics.median(tm_ok) if all_reached and len(tm_ok) == len(pairs) else None
    return {
        "seeds": len(pairs),
        "surrogate_reached": sum(1 for _, s in pairs if s.generation_to_target is not None),
        "evaluation_speedups": ev,
        "time_speedups": tm,
        "median_evaluation_speedup": median_ev,
        "median_time_speedup": median_tm,
        "final_ratios": [s.final_total / b.final_total for b, s in pairs],
        "faster_by_evaluations": median_ev is not None and median_ev > 1.0,
        "faster_by_time": median_tm is not None and median_tm > 1.0,
    }

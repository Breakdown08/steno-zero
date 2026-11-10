"""Checks 33-34: summarize and compare_runs (no torch)."""

import dataclasses
from typing import Any

import pytest

from steno_zero.compare import RunStats, compare_runs, summarize
from steno_zero.evolve import EvolveParams, EvolveResult, evolve
from steno_zero.params import PenaltyParams
from steno_zero.simulate import evaluate
from steno_zero.table import Table
from tests.helpers import costs, fragment

HORIZON: float = 1_000_000.0
SUMMARY_ORDER: list[str] = [
    "seeds", "surrogate_reached", "evaluation_speedups", "time_speedups", "median_evaluation_speedup",
    "median_time_speedup", "final_ratios", "faster_by_evaluations", "faster_by_time",
]  # fmt: skip


def stats(
    seed: int,
    mode: str,
    evals: int | None,
    secs: float | None,
    final: float = 100.0,
    gen: int | None = 1,
) -> RunStats:
    return RunStats(
        seed=seed,
        mode=mode,
        final_total=final,
        exact_evaluations=500,
        screened=0 if mode == "baseline" else 100,
        wall_s=20.0,
        target=100.0,
        generation_to_target=gen,
        evaluations_to_target=evals,
        seconds_to_target=secs,
    )


def pair_runs() -> list[RunStats]:
    return [
        stats(0, "baseline", 100, 10.0, 100.0),
        stats(0, "surrogate", 50, 5.0, 98.0),
        stats(1, "baseline", 90, 9.0, 200.0),
        stats(1, "surrogate", 60, 12.0, 190.0),
    ]


def test_summarize_speedups() -> None:
    summary: dict[str, Any] = summarize(pair_runs())
    assert list(summary) == SUMMARY_ORDER
    assert summary["seeds"] == 2
    assert summary["surrogate_reached"] == 2
    assert summary["evaluation_speedups"] == [2.0, 1.5]
    assert summary["median_evaluation_speedup"] == 1.75
    assert summary["time_speedups"] == [2.0, 0.75]
    assert summary["median_time_speedup"] == 1.375
    assert summary["faster_by_evaluations"] is True
    assert summary["faster_by_time"] is True
    assert summary["final_ratios"] == pytest.approx([0.98, 0.95])


def test_summarize_when_surrogate_misses_a_seed() -> None:
    runs: list[RunStats] = pair_runs()
    runs[3] = stats(1, "surrogate", None, None, 190.0, gen=None)
    summary: dict[str, Any] = summarize(runs)
    assert summary["surrogate_reached"] == 1
    assert summary["evaluation_speedups"] == [2.0, None]
    assert summary["time_speedups"] == [2.0, None]
    assert summary["median_evaluation_speedup"] is None
    assert summary["median_time_speedup"] is None
    assert summary["faster_by_evaluations"] is False
    assert summary["faster_by_time"] is False


def test_summarize_not_faster_when_median_is_at_most_one() -> None:
    runs: list[RunStats] = [
        stats(0, "baseline", 100, 10.0),
        stats(0, "surrogate", 100, 20.0),
    ]
    summary: dict[str, Any] = summarize(runs)
    assert summary["median_evaluation_speedup"] == 1.0
    assert summary["faster_by_evaluations"] is False
    assert summary["median_time_speedup"] == 0.5
    assert summary["faster_by_time"] is False


def test_summarize_needs_a_pair_per_seed() -> None:
    runs: list[RunStats] = pair_runs()
    with pytest.raises(ValueError):
        summarize(runs[:3])
    with pytest.raises(ValueError):
        summarize([runs[0], runs[0], runs[1]])


def exact(tables: list[Table]) -> list[float]:
    return [evaluate(fragment(), t, costs(), PenaltyParams(), HORIZON).total for t in tables]


def compare(seeds: list[int], oversample: int = 3) -> list[RunStats]:
    return compare_runs(
        fragment(),
        costs(),
        PenaltyParams(),
        HORIZON,
        EvolveParams(population=8, generations=4),
        seeds,
        oversample,
        exact,
    )


def test_compare_runs() -> None:
    runs: list[RunStats] = compare([0, 1])
    assert [(r.seed, r.mode) for r in runs] == [
        (0, "baseline"),
        (0, "surrogate"),
        (1, "baseline"),
        (1, "surrogate"),
    ]
    i: int
    for i in (0, 2):
        base: RunStats = runs[i]
        sur: RunStats = runs[i + 1]
        assert base.screened == 0
        assert base.target == base.final_total
        assert base.generation_to_target is not None
        assert base.generation_to_target <= 4
        assert sur.screened == 4 * 3 * 6 == 72
        assert sur.target == base.final_total
        res: EvolveResult = evolve(
            fragment(),
            costs(),
            PenaltyParams(),
            HORIZON,
            EvolveParams(seed=base.seed, population=8, generations=4),
        )
        assert base.final_total == res.history[-1].best_total
        assert base.exact_evaluations == res.history[-1].evaluations
        assert base.evaluations_to_target is not None
        filtered: EvolveResult = evolve(
            fragment(),
            costs(),
            PenaltyParams(),
            HORIZON,
            EvolveParams(seed=base.seed, population=8, generations=4),
            screen=exact,
            oversample=3,
        )
        assert sur.exact_evaluations == filtered.history[-1].evaluations
        assert sur.final_total == filtered.history[-1].best_total


def test_compare_runs_is_repeatable() -> None:
    skip: set[str] = {"wall_s", "seconds_to_target"}

    def stable(runs: list[RunStats]) -> list[dict[str, Any]]:
        return [{k: v for k, v in dataclasses.asdict(r).items() if k not in skip} for r in runs]

    assert stable(compare([0, 1])) == stable(compare([0, 1]))


def test_compare_runs_validation() -> None:
    with pytest.raises(ValueError):
        compare([0, 1], oversample=1)
    with pytest.raises(ValueError):
        compare([])

"""Checks 1-8: evolve with a screen filter (no torch)."""

from collections.abc import Callable

import pytest

from steno_zero.evolve import EvolveParams, EvolveResult, GenerationRecord, Screen, evolve
from steno_zero.params import PenaltyParams
from steno_zero.simulate import Score, evaluate
from steno_zero.table import Table
from tests.helpers import costs, fragment

HORIZON: float = 1_000_000.0


def run(
    params: EvolveParams,
    screen: Screen | None = None,
    oversample: int = 1,
    workers: int = 1,
    on_evaluated: Callable[[int, list[Table], list[Score]], None] | None = None,
) -> EvolveResult:
    return evolve(
        fragment(),
        costs(),
        PenaltyParams(),
        HORIZON,
        params,
        workers,
        screen=screen,
        oversample=oversample,
        on_evaluated=on_evaluated,
    )


def exact_screen(tables: list[Table]) -> list[float]:
    return [evaluate(fragment(), t, costs(), PenaltyParams(), HORIZON).total for t in tables]


def test_oversample_one_equals_no_screen() -> None:
    params: EvolveParams = EvolveParams(seed=0, population=8, generations=5)
    sizes: list[int] = []

    def s(tables: list[Table]) -> list[float]:
        sizes.append(len(tables))
        return [0.0] * len(tables)

    plain: EvolveResult = run(params)
    filtered: EvolveResult = run(params, screen=s, oversample=1)
    assert filtered.history == plain.history
    assert filtered.best == plain.best
    assert sizes == [6] * 5


def test_screen_called_with_oversampled_batches() -> None:
    params: EvolveParams = EvolveParams(seed=0, population=8, elite=2, generations=4)
    sizes: list[int] = []

    def s(tables: list[Table]) -> list[float]:
        sizes.append(len(tables))
        return [float(i) for i in range(len(tables))]

    run(params, screen=s, oversample=3)
    assert sizes == [18] * 4


def history_of(seed: int, screen: Screen | None, oversample: int) -> tuple[GenerationRecord, ...]:
    return run(EvolveParams(seed=seed, population=8, generations=3), screen, oversample).history


def test_screen_order_decides_generation_one() -> None:
    def first(tables: list[Table]) -> list[float]:
        return [float(i) for i in range(len(tables))]

    def last(tables: list[Table]) -> list[float]:
        return [-float(i) for i in range(len(tables))]

    seed: int
    differs: bool = False
    for seed in range(10):
        plain: tuple[GenerationRecord, ...] = history_of(seed, None, 1)
        preferring_first: tuple[GenerationRecord, ...] = history_of(seed, first, 3)
        assert preferring_first[:2] == plain[:2]
        preferring_last: tuple[GenerationRecord, ...] = history_of(seed, last, 3)
        assert preferring_last[0] == plain[0]
        if preferring_last[1] != plain[1]:
            differs = True
            break
    assert differs


def test_final_total_is_exact() -> None:
    params: EvolveParams = EvolveParams(seed=0, population=8, generations=4)
    res: EvolveResult = run(params, screen=exact_screen, oversample=3)
    exact: Score = evaluate(fragment(), res.best, costs(), PenaltyParams(), HORIZON)
    assert res.score == exact
    assert res.history[-1].best_total == res.score.total
    assert res.history[-1].best_total == exact.total


def test_evaluations_growth_is_bounded() -> None:
    params: EvolveParams = EvolveParams(seed=0, population=8, generations=5)
    res: EvolveResult = run(params, screen=exact_screen, oversample=3)
    prev: int = res.history[0].evaluations
    rec: GenerationRecord
    for rec in res.history[1:]:
        assert 0 <= rec.evaluations - prev <= params.population - params.elite
        prev = rec.evaluations


def test_on_evaluated_reports_every_generation() -> None:
    params: EvolveParams = EvolveParams(seed=0, population=8, generations=4)
    calls: list[tuple[int, list[Table], list[Score]]] = []

    def on_evaluated(generation: int, fresh: list[Table], scores: list[Score]) -> None:
        calls.append((generation, list(fresh), list(scores)))

    res: EvolveResult = run(params, screen=exact_screen, oversample=2, on_evaluated=on_evaluated)
    assert [c[0] for c in calls] == list(range(params.generations + 1))
    assert sum(len(c[1]) for c in calls) == res.history[-1].evaluations
    assert sum(len(c[1]) for c in calls) > 0
    _generation: int
    fresh: list[Table]
    scores: list[Score]
    for _generation, fresh, scores in calls:
        assert len(fresh) == len(scores)
        t: Table
        s: Score
        for t, s in zip(fresh, scores, strict=True):
            assert s == evaluate(fragment(), t, costs(), PenaltyParams(), HORIZON)


def test_invalid_arguments() -> None:
    params: EvolveParams = EvolveParams(seed=0, population=8, generations=2)
    with pytest.raises(ValueError):
        run(params, screen=exact_screen, oversample=0)
    with pytest.raises(ValueError):
        run(params, screen=None, oversample=2)

    def short(tables: list[Table]) -> list[float]:
        return [0.0] * (len(tables) - 1)

    with pytest.raises(ValueError):
        run(params, screen=short, oversample=2)


def test_workers_do_not_change_result() -> None:
    params: EvolveParams = EvolveParams(seed=0, population=8, generations=4)
    one: EvolveResult = run(params, screen=exact_screen, oversample=3, workers=1)
    two: EvolveResult = run(params, screen=exact_screen, oversample=3, workers=2)
    assert one.history == two.history
    assert one.best == two.best
    assert one.history[-1].evaluations > 0

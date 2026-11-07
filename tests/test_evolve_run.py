"""Checks 16-25: evolve."""

import functools

import pytest

from steno_zero.evolve import EvolveParams, EvolveResult, GenerationRecord, evolve
from steno_zero.params import PenaltyParams
from steno_zero.simulate import Score, evaluate
from tests.helpers import costs, fragment

HORIZON: float = 1_000_000.0


def small_params() -> EvolveParams:
    return EvolveParams(seed=0, population=8, generations=10)


def run(params: EvolveParams, workers: int = 1) -> EvolveResult:
    return evolve(fragment(), costs(), PenaltyParams(), HORIZON, params, workers=workers)


@functools.cache
def small() -> EvolveResult:
    return run(small_params())


def test_history_length_and_numbers() -> None:
    h: tuple[GenerationRecord, ...] = small().history
    assert len(h) == 11
    assert [r.generation for r in h] == list(range(11))


def test_records_and_ordering() -> None:
    h: tuple[GenerationRecord, ...] = small().history
    assert h[0].record is True
    i: int
    for i in range(1, len(h)):
        assert h[i].best_total <= h[i - 1].best_total
        assert h[i].record == (h[i].best_total < h[i - 1].best_total)
    r: GenerationRecord
    for r in h:
        assert r.gen_best_total >= r.best_total
        assert r.mean_total >= r.gen_best_total


def test_elite_keeps_generation_best_at_record() -> None:
    r: GenerationRecord
    for r in small().history:
        assert r.gen_best_total == r.best_total


def test_result_matches_evaluate() -> None:
    res: EvolveResult = small()
    score: Score = evaluate(fragment(), res.best, costs(), PenaltyParams(), HORIZON)
    assert res.score == score
    last: GenerationRecord = res.history[-1]
    assert res.score.total == last.best_total
    assert last.entries == len(res.best)
    assert last.t_char == res.score.t_char
    assert last.memory == res.score.memory
    assert last.confusion == res.score.confusion


def test_evaluations_counter() -> None:
    h: tuple[GenerationRecord, ...] = small().history
    assert 1 <= h[0].evaluations <= small_params().population
    i: int
    for i in range(1, len(h)):
        step: int = h[i].evaluations - h[i - 1].evaluations
        assert 0 <= step <= small_params().population - small_params().elite


def test_on_generation_callback() -> None:
    seen: list[GenerationRecord] = []
    res: EvolveResult = evolve(
        fragment(), costs(), PenaltyParams(), HORIZON, small_params(), on_generation=seen.append
    )
    assert len(seen) == small_params().generations + 1
    assert tuple(seen) == res.history


def test_reproducible_and_seed_matters() -> None:
    again: EvolveResult = run(small_params())
    assert again.history == small().history
    assert again.best == small().best
    other: EvolveResult = run(EvolveParams(seed=1, population=8, generations=10))
    assert other.history != small().history


def test_evolution_improves() -> None:
    res: EvolveResult = run(EvolveParams(seed=0, population=16, generations=30))
    assert res.history[-1].best_total < res.history[0].best_total


def test_workers_do_not_change_result() -> None:
    params: EvolveParams = EvolveParams(seed=0, population=8, generations=5)
    one: EvolveResult = run(params, workers=1)
    two: EvolveResult = run(params, workers=2)
    assert one.history == two.history
    assert one.best == two.best


def test_value_errors() -> None:
    with pytest.raises(ValueError):
        run(small_params(), workers=0)
    with pytest.raises(ValueError):
        evolve("а", costs(), PenaltyParams(), HORIZON, small_params())

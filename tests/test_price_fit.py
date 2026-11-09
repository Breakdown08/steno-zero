"""Checks 27-35: the models on the synthetic measurements."""

import dataclasses
from typing import Any

import pandas as pd
import pytest

from steno_zero.chords import allowed_chords
from steno_zero.drill import DrillLog
from steno_zero.keyboard import Blocked, KeyboardProfile, profile_sha256
from steno_zero.price import FEATURE_NAMES, TIME_MODELS, PriceFit, presentations_frame
from steno_zero.trainer import chord_label
from tests.drill_helpers import Plan
from tests.keyboard_helpers import P1
from tests.price_helpers import (
    extra_log,
    fit,
    keyboard_of,
    main_fit,
    main_frame,
    main_plan,
    p1_fit,
    p1_frame,
    p1_logs,
    synth_logs,
    truth,
    without,
)

REPORT_KEYS: set[str] = {
    "format",
    "version",
    "target",
    "max_keys",
    "seed",
    "folds",
    "max_ms",
    "keyboard",
    "rows",
    "time_rows",
    "misses",
    "dropped_slow",
    "chords_seen",
    "sessions",
    "time",
    "chosen",
    "ridge_coefficients",
    "miss",
    "suspect_chords",
    "features",
}
PRICES_KEYS: set[str] = {
    "format",
    "version",
    "target",
    "model",
    "miss_model",
    "max_keys",
    "seed",
    "keyboard",
    "available",
    "unavailable",
    "sessions",
    "prices",
}


def check_ridge_thresholds(result: PriceFit) -> None:
    time: dict[str, dict[str, Any]] = result.report["time"]
    base: dict[str, Any] = time["baseline"]
    assert time["ridge"]["mae_ms"] <= 60
    assert time["ridge"]["r2"] >= 0.9
    assert base["mae_ms"] >= 100
    assert base["r2"] <= 0.8
    assert time["boosting"]["mae_ms"] <= 0.6 * base["mae_ms"]
    assert time["ridge"]["mae_ms"] <= 0.5 * base["mae_ms"]


def test_ridge_recovers_the_dependence_and_beats_the_baseline() -> None:
    check_ridge_thresholds(main_fit())


def test_chosen_is_the_smallest_mae() -> None:
    result: PriceFit = main_fit()
    time: dict[str, dict[str, Any]] = result.report["time"]
    assert set(time) == set(TIME_MODELS)
    best: str = min(TIME_MODELS, key=lambda m: time[m]["mae_ms"])
    assert result.report["chosen"] == best
    assert result.prices["model"] == best


def test_unseen_chords_get_the_true_price() -> None:
    plan: Plan = without(main_plan(), lambda c: c % 17 == 0)
    frame: pd.DataFrame = presentations_frame(synth_logs(plan), 5)
    assert not (frame["target"] % 17 == 0).any()
    result: PriceFit = fit(frame, model="ridge")
    errors: list[float] = [
        abs(row["time_ms"] - truth(row["chord"])) for row in result.prices["prices"] if row["chord"] % 17 == 0
    ]
    assert len(errors) == len([c for c in allowed_chords(6) if c % 17 == 0])
    assert sum(errors) / len(errors) <= 25
    assert max(errors) <= 60


def test_prices_list_every_chord_without_profile() -> None:
    prices: dict[str, Any] = main_fit().prices
    rows: list[dict[str, Any]] = prices["prices"]
    assert [r["chord"] for r in rows] == list(allowed_chords(6))
    assert all(r["available"] is True for r in rows)
    assert all(0 < r["miss_prob"] < 1 for r in rows)
    assert all(r["time_ms"] is not None for r in rows)
    assert all(r["label"] == chord_label(r["chord"]) for r in rows)
    assert all(r["keys"] == r["chord"].bit_count() for r in rows)
    assert prices["keyboard"] is None
    assert prices["unavailable"] == 0
    assert prices["available"] == 847


def test_prices_with_profile() -> None:
    result: PriceFit = p1_fit()
    rows: dict[int, dict[str, Any]] = {r["chord"]: r for r in result.prices["prices"]}
    assert list(rows) == list(allowed_chords(6))
    c: int
    for c in (152, 153):
        assert rows[c]["available"] is False
        assert rows[c]["time_ms"] is None
        assert rows[c]["miss_prob"] is None
    assert rows[88]["available"] is True
    assert rows[88]["time_ms"] is not None
    assert result.prices["available"] == 783
    assert result.prices["unavailable"] == 64
    assert result.prices["keyboard"] == {"name": "test", "sha256": profile_sha256(P1)}
    assert result.report["keyboard"] == {"name": "test", "sha256": profile_sha256(P1)}
    check_ridge_thresholds(result)


def test_profile_must_match_the_frame() -> None:
    with pytest.raises(ValueError):
        fit(p1_frame(), profile=None)
    other: KeyboardProfile = dataclasses.replace(P1, blocked=(Blocked(152, True),))
    assert profile_sha256(other) != profile_sha256(P1)
    with pytest.raises(ValueError):
        fit(p1_frame(), profile=other)
    with pytest.raises(ValueError):
        fit(main_frame(), profile=P1)


def test_a_blocked_target_in_the_frame_is_an_error() -> None:
    bad: DrillLog = extra_log([(152, 152)] * 8, keyboard_of(P1), session="blocked")
    frame: pd.DataFrame = presentations_frame([*p1_logs(), bad], 5)
    with pytest.raises(ValueError):
        fit(frame, profile=P1)


def test_miss_models() -> None:
    result: PriceFit = main_fit()
    miss: dict[str, Any] | None = result.report["miss"]
    assert miss is not None
    assert miss["logistic"]["log_loss"] < miss["baseline"]["log_loss"]
    assert miss["chosen"] in ("baseline", "logistic")
    assert result.prices["miss_model"] == miss["chosen"]
    assert set(miss["baseline"]) == {"log_loss", "brier"}


def test_no_misses_means_no_miss_model() -> None:
    frame: pd.DataFrame = presentations_frame(synth_logs(main_plan()[:12], misses=False), 5)
    result: PriceFit = fit(frame, model="ridge")
    assert result.report["miss"] is None
    assert result.report["misses"] == 0
    assert result.prices["miss_model"] == "baseline"
    assert all(0 < r["miss_prob"] < 1 for r in result.prices["prices"])


def test_suspect_chords_found() -> None:
    plan: Plan = without(main_plan(), lambda c: c == 412)
    warm: list[tuple[int, int]] = [(1, 1)] * 5
    logs: list[DrillLog] = [
        *synth_logs(plan),
        extra_log([*warm, (412, 412 & ~128), (412, 412 & ~128), (412, 412 & ~128)]),
    ]
    frame: pd.DataFrame = presentations_frame(logs, 5)
    result: PriceFit = fit(frame, model="ridge")
    expected: dict[str, Any] = {"chord": 412, "label": chord_label(412), "presentations": 3}
    assert expected in result.report["suspect_chords"]


def test_suspect_chords_are_only_all_miss_strict_subsets() -> None:
    frame: pd.DataFrame = main_frame()
    suspects: list[dict[str, Any]] = main_fit().report["suspect_chords"]
    chords: list[int] = [s["chord"] for s in suspects]
    assert chords == sorted(chords)
    s: dict[str, Any]
    for s in suspects:
        rows: pd.DataFrame = frame[frame["target"] == s["chord"]]
        assert len(rows) >= 2
        assert rows["miss"].all()
        assert ((rows["typed"] & rows["target"] == rows["typed"]) & (rows["typed"] != rows["target"])).all()
        assert s["presentations"] == len(rows)
        assert s["label"] == chord_label(s["chord"])


def test_report_fields() -> None:
    result: PriceFit = main_fit()
    frame: pd.DataFrame = main_frame()
    report: dict[str, Any] = result.report
    assert set(report) == REPORT_KEYS
    assert report["format"] == "steno-zero/chord-price-report"
    assert report["version"] == 1
    assert (report["target"], report["max_keys"], report["seed"], report["folds"]) == ("total", 6, 0, 5)
    assert report["max_ms"] == 5000.0
    assert report["rows"] == len(frame)
    assert report["misses"] == int(frame["miss"].sum())
    assert report["time_rows"] + report["dropped_slow"] + report["misses"] == report["rows"]
    assert report["chords_seen"] == frame.loc[~frame["miss"], "target"].nunique()
    assert report["features"] == list(FEATURE_NAMES)
    assert [s["session"] for s in report["sessions"]] == [f"s{b}" for b in range(30)]
    assert result.prices["sessions"] == [f"s{b}" for b in range(30)]
    assert set(report["sessions"][0]) == {
        "session",
        "block",
        "started",
        "presentations",
        "median_ms",
        "miss_rate",
    }
    assert report["sessions"][0]["presentations"] == 95
    assert list(report["ridge_coefficients"]) == ["intercept", *FEATURE_NAMES]
    assert set(result.prices) == PRICES_KEYS
    assert result.prices["format"] == "steno-zero/chord-prices"
    assert result.prices["version"] == 1


def test_ridge_coefficients_have_the_sign_of_the_truth() -> None:
    coefficients: dict[str, float] = main_fit().report["ridge_coefficients"]
    assert coefficients["holes"] > 100
    assert coefficients["both_hands"] > 50
    assert coefficients["keys"] > 30


def test_motor_target() -> None:
    result: PriceFit = fit(main_frame(), target="motor", model="ridge")
    assert result.report["target"] == "motor"
    assert result.prices["target"] == "motor"
    assert result.report["time"]["ridge"]["r2"] >= 0.9


def test_slow_rows_are_dropped_but_every_chord_is_priced() -> None:
    result: PriceFit = fit(main_frame(), max_ms=700.0)
    assert result.report["dropped_slow"] > 0
    assert result.report["max_ms"] == 700.0
    rows: list[dict[str, Any]] = result.prices["prices"]
    assert any(truth(r["chord"]) > 700 for r in rows)
    assert all(r["time_ms"] is not None for r in rows)
    assert [r["chord"] for r in rows] == list(allowed_chords(6))


@pytest.mark.parametrize(
    "changes",
    [
        {"target": "x"},
        {"model": "x"},
        {"folds": 1},
        {"folds": 1000},
        {"max_keys": 4},
        {"max_keys": 11},
        {"max_keys": 1},
        {"max_ms": 0.0},
        {"max_ms": -5.0},
    ],
)
def test_fit_errors(changes: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        fit(main_frame(), **changes)


def test_max_keys_error_mentions_the_option() -> None:
    with pytest.raises(ValueError, match="--max-keys"):
        fit(main_frame(), max_keys=4)


def walk(value: object) -> list[object]:
    if isinstance(value, dict):
        return [x for v in value.values() for x in walk(v)]
    if isinstance(value, list):
        return [x for v in value for x in walk(v)]
    return [value]


def test_deterministic_and_plain_python_numbers() -> None:
    first: PriceFit = fit(main_frame(), model="ridge")
    second: PriceFit = fit(main_frame(), model="ridge")
    assert first.prices == second.prices
    assert first.report == second.report
    leaf: object
    for leaf in walk(first.prices) + walk(first.report):
        assert type(leaf) in (int, float, str, bool, type(None)), type(leaf)


def test_rounding() -> None:
    rows: list[dict[str, Any]] = main_fit().prices["prices"]
    assert all(r["time_ms"] == round(r["time_ms"], 1) for r in rows)
    assert all(r["miss_prob"] == round(r["miss_prob"], 6) for r in rows)
    time: dict[str, dict[str, Any]] = main_fit().report["time"]
    assert all(m["mae_ms"] == round(m["mae_ms"], 1) for m in time.values())
    assert all(m["r2"] == round(m["r2"], 6) for m in time.values())


def test_other_profile_object_with_same_content_is_accepted() -> None:
    same: KeyboardProfile = dataclasses.replace(P1)
    assert same is not P1
    assert fit(p1_frame(), model="ridge", profile=same).prices["available"] == 783

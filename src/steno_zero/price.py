"""Chord prices from measurements of random chords: features, cross-validated models, price table."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from numpy.typing import NDArray
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import brier_score_loss, log_loss, mean_absolute_error, r2_score
from sklearn.model_selection import GroupKFold

from steno_zero.chords import N_CHORDS, N_KEYS, allowed_chords, check_max_keys
from steno_zero.drill import DrillLog, Presentation
from steno_zero.keyboard import KeyboardProfile, available_chords, is_available, profile_sha256
from steno_zero.trainer import chord_label

FINGER: tuple[int, ...] = (0, 1, 2, 3, 3, 3, 3, 2, 1, 0)
FEATURE_NAMES: tuple[str, ...] = (
    "keys",
    "left",
    "right",
    "both_hands",
    "key_0",
    "key_1",
    "key_2",
    "key_3",
    "key_4",
    "key_5",
    "key_6",
    "key_7",
    "key_8",
    "key_9",
    "index_pairs",
    "adjacent",
    "span",
    "holes",
    "mirror",
)
TARGETS: tuple[str, ...] = ("total", "motor")
TIME_MODELS: tuple[str, ...] = ("baseline", "ridge", "boosting")
MISS_MODELS: tuple[str, ...] = ("baseline", "logistic")
MIN_MISSES: int = 30
PRICES_FORMAT: str = "steno-zero/chord-prices"
REPORT_FORMAT: str = "steno-zero/chord-price-report"
PRICE_VERSION: int = 1
SKIP_FIRST: int = 5
MAX_MS: float = 5000.0
FOLDS: int = 5


@dataclass(frozen=True)
class PriceFit:
    prices: dict[str, Any]
    report: dict[str, Any]


type Floats = NDArray[np.float64]
type Keyboard = tuple[str, str] | None
type Predictor = Callable[[Floats, Floats, Floats], Floats]  # train X, train y, test X -> test predictions

HANDS: tuple[range, range] = (range(0, 5), range(5, 10))
ADJACENT: tuple[tuple[int, int], ...] = ((0, 1), (1, 2), (2, 3), (3, 4), (5, 6), (6, 7), (7, 8), (8, 9))
INDEX_PAIRS: tuple[tuple[int, int], ...] = ((3, 4), (5, 6))


def chord_features(chord: int) -> dict[str, int]:
    if not 1 <= chord <= N_CHORDS:
        raise ValueError(f"chord out of range 1..{N_CHORDS}: {chord}")
    pressed: list[bool] = [bool(chord >> k & 1) for k in range(N_KEYS)]
    counts: list[int] = [sum(pressed[k] for k in hand) for hand in HANDS]
    span: int = 0
    holes: int = 0
    hand: range
    for hand in HANDS:
        fingers: set[int] = {FINGER[k] for k in hand if pressed[k]}
        if fingers:
            span += max(fingers) - min(fingers)
            holes += max(fingers) - min(fingers) + 1 - len(fingers)
    left_keys: set[int] = {k for k in HANDS[0] if pressed[k]}
    right_keys: set[int] = {k for k in HANDS[1] if pressed[k]}
    values: dict[str, int] = {
        "keys": chord.bit_count(),
        "left": counts[0],
        "right": counts[1],
        "both_hands": int(counts[0] > 0 and counts[1] > 0),
    }
    k: int
    for k in range(N_KEYS):
        values[f"key_{k}"] = int(pressed[k])
    values["index_pairs"] = sum(pressed[a] and pressed[b] for a, b in INDEX_PAIRS)
    values["adjacent"] = sum(pressed[a] and pressed[b] for a, b in ADJACENT)
    values["span"] = span
    values["holes"] = holes
    values["mirror"] = int(counts[0] > 0 and right_keys == {N_KEYS - 1 - k for k in left_keys})
    return {name: values[name] for name in FEATURE_NAMES}


def features_frame(chords: Sequence[int]) -> pd.DataFrame:
    rows: list[list[int]] = [list(chord_features(c).values()) for c in chords]
    return pd.DataFrame(
        rows, index=pd.Index(list(chords), name="chord"), columns=list(FEATURE_NAMES), dtype="int64"
    )


def _keyboard_text(keyboard: Keyboard) -> str:
    return "none" if keyboard is None else f"{keyboard[0]} {keyboard[1][:8]}"


def logs_keyboard(logs: Sequence[DrillLog]) -> tuple[str, str] | None:
    if not logs:
        raise ValueError("no logs")
    groups: dict[Keyboard, int] = {}
    log: DrillLog
    for log in logs:
        groups[log.keyboard] = groups.get(log.keyboard, 0) + 1
    if len(groups) > 1:
        listed: str = ", ".join(f"{_keyboard_text(k)} ({n} sessions)" for k, n in groups.items())
        raise ValueError(f"logs use different keyboards: {listed}")
    return logs[0].keyboard


def presentations_frame(logs: Sequence[DrillLog], skip_first: int) -> pd.DataFrame:
    keyboard: Keyboard = logs_keyboard(logs)
    if skip_first < 0:
        raise ValueError("skip_first must not be negative")
    names: list[str] = [log.session for log in logs]
    if len(set(names)) != len(names):
        raise ValueError("the same session is given twice")
    rows: list[tuple[Any, ...]] = []
    log: DrillLog
    for log in sorted(logs, key=lambda x: (x.started, x.session)):
        p: Presentation
        for p in log.presentations[skip_first:]:
            rows.append(
                (
                    log.session,
                    log.block,
                    log.started,
                    p.i,
                    p.target,
                    p.typed,
                    p.typed != p.target,
                    p.shown_ms,
                    p.down_ms,
                    p.up_ms,
                    p.up_ms - p.shown_ms,
                    p.up_ms - p.down_ms,
                )
            )
    if not rows:
        raise ValueError(f"no presentations left after skipping the first {skip_first} of each session")
    base: pd.DataFrame = pd.DataFrame(
        rows,
        columns=[
            "session",
            "block",
            "started",
            "i",
            "target",
            "typed",
            "miss",
            "shown_ms",
            "down_ms",
            "up_ms",
            "total_ms",
            "motor_ms",
        ],
    )
    features: pd.DataFrame = features_frame([int(t) for t in base["target"]]).reset_index(drop=True)
    frame: pd.DataFrame = pd.concat([base, features], axis=1)
    frame.attrs["keyboard"] = keyboard
    return frame


def _baseline_time(x_train: Floats, y_train: Floats, x_test: Floats) -> Floats:
    keys: Floats = x_train[:, 0]
    overall: float = float(y_train.mean())
    means: dict[float, float] = {float(k): float(y_train[keys == k].mean()) for k in np.unique(keys)}
    return np.array([means.get(float(k), overall) for k in x_test[:, 0]], dtype=np.float64)


def _ridge(x_train: Floats, y_train: Floats, x_test: Floats) -> Floats:
    return np.asarray(Ridge(alpha=1.0).fit(x_train, y_train).predict(x_test), dtype=np.float64)


def _boosting_for(seed: int) -> Predictor:
    def boosting(x_train: Floats, y_train: Floats, x_test: Floats) -> Floats:
        model: HistGradientBoostingRegressor = HistGradientBoostingRegressor(
            random_state=seed, early_stopping=False
        )
        return np.asarray(model.fit(x_train, y_train).predict(x_test), dtype=np.float64)

    return boosting


def _baseline_miss(x_train: Floats, y_train: Floats, x_test: Floats) -> Floats:
    keys: Floats = x_train[:, 0]
    overall: float = (float(y_train.sum()) + 1.0) / (len(y_train) + 2.0)
    rates: dict[float, float] = {
        float(k): (float(y_train[keys == k].sum()) + 1.0) / (float((keys == k).sum()) + 2.0)
        for k in np.unique(keys)
    }
    return np.array([rates.get(float(k), overall) for k in x_test[:, 0]], dtype=np.float64)


def _logistic(x_train: Floats, y_train: Floats, x_test: Floats) -> Floats:
    model: LogisticRegression = LogisticRegression(max_iter=1000).fit(x_train, y_train)
    return np.asarray(model.predict_proba(x_test)[:, 1], dtype=np.float64)


def _out_of_fold(
    predictor: Predictor, x: Floats, y: Floats, groups: NDArray[np.int64], folds: int, seed: int
) -> Floats:
    out: Floats = np.zeros(len(y), dtype=np.float64)
    splitter: GroupKFold = GroupKFold(n_splits=folds, shuffle=True, random_state=seed)
    train: NDArray[np.intp]
    test: NDArray[np.intp]
    for train, test in splitter.split(x, y, groups):
        out[test] = predictor(x[train], y[train], x[test])
    return out


def _chord_mae(y: Floats, predicted: Floats, groups: NDArray[np.int64]) -> float | None:
    errors: list[float] = []
    chord: int
    for chord in np.unique(groups):
        mask: NDArray[np.bool_] = groups == chord
        if mask.sum() >= 2:
            errors.append(abs(float(y[mask].mean()) - float(predicted[mask].mean())))
    return float(np.mean(errors)) if errors else None


def _round(value: float | None, digits: int) -> float | None:
    return None if value is None else round(float(value), digits)


def _check_profile(frame: pd.DataFrame, profile: KeyboardProfile | None) -> Keyboard:
    recorded: Any = frame.attrs.get("keyboard")
    keyboard: Keyboard = None if recorded is None else (str(recorded[0]), str(recorded[1]))
    if keyboard is None:
        if profile is not None:
            raise ValueError("the logs were taken without a keyboard profile, but a profile was given")
        return None
    if profile is None:
        raise ValueError(
            f"the logs were taken on the keyboard profile {_keyboard_text(keyboard)}; "
            "pass it with --keyboard data/keyboards/NAME.json"
        )
    if (profile.name, profile_sha256(profile)) != keyboard:
        raise ValueError(
            f"the logs were taken on the keyboard profile {_keyboard_text(keyboard)}, "
            f"but the given profile is {_keyboard_text((profile.name, profile_sha256(profile)))}"
        )
    chord: int
    for chord in sorted({int(t) for t in frame["target"]}):
        if not is_available(chord, profile):
            raise ValueError(f"target {chord} ({chord_label(chord)}) is blocked on the keyboard profile")
    return keyboard


def _suspects(frame: pd.DataFrame) -> list[dict[str, Any]]:
    typed_by: dict[int, list[int]] = {}
    chord: int
    typed: int
    for chord, typed in zip(frame["target"].tolist(), frame["typed"].tolist(), strict=True):
        typed_by.setdefault(chord, []).append(typed)
    return [
        {"chord": chord, "label": chord_label(chord), "presentations": len(group)}
        for chord, group in sorted(typed_by.items())
        if len(group) >= 2 and all(t != chord and t & chord == t for t in group)
    ]


def _sessions(frame: pd.DataFrame, column: str, max_ms: float) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    session: str
    rows: pd.DataFrame
    ordered: list[str] = list(dict.fromkeys(str(s) for s in frame["session"]))
    for session in ordered:
        rows = frame[frame["session"] == session]
        fast: pd.DataFrame = rows[~rows["miss"] & (rows[column] <= max_ms)]
        out.append(
            {
                "session": session,
                "block": int(rows["block"].iloc[0]),
                "started": str(rows["started"].iloc[0]),
                "presentations": len(rows),
                "median_ms": _round(float(fast[column].median()), 1) if len(fast) else None,
                "miss_rate": round(float(rows["miss"].mean()), 6),
            }
        )
    return out


def fit_prices(
    frame: pd.DataFrame,
    target: str,
    model: str,
    max_keys: int,
    folds: int,
    seed: int,
    max_ms: float,
    profile: KeyboardProfile | None,
) -> PriceFit:
    if target not in TARGETS:
        raise ValueError(f"target must be one of {', '.join(TARGETS)}: {target!r}")
    if model not in ("auto", *TIME_MODELS):
        raise ValueError(f"model must be one of auto, {', '.join(TIME_MODELS)}: {model!r}")
    if folds < 2:
        raise ValueError("folds must be at least 2")
    check_max_keys(max_keys)
    if not max_ms > 0:
        raise ValueError("max_ms must be positive")
    keyboard: Keyboard = _check_profile(frame, profile)
    too_long: list[int] = sorted({int(t) for t in frame["target"] if int(t).bit_count() > max_keys})
    if too_long:
        raise ValueError(f"frame has targets with more than {max_keys} keys: {too_long}; raise --max-keys")
    column: str = f"{target}_ms"
    miss: NDArray[np.bool_] = frame["miss"].to_numpy(dtype=bool)
    features: Floats = frame[list(FEATURE_NAMES)].to_numpy(dtype=np.float64)
    chords: NDArray[np.int64] = frame["target"].to_numpy(dtype=np.int64)
    goal: Floats = frame[column].to_numpy(dtype=np.float64)
    keep: NDArray[np.bool_] = ~miss & (goal <= max_ms)
    dropped_slow: int = int((~miss & (goal > max_ms)).sum())
    x_time: Floats = features[keep]
    y_time: Floats = goal[keep]
    g_time: NDArray[np.int64] = chords[keep]
    chords_seen: int = len(np.unique(g_time))
    if chords_seen < folds:
        raise ValueError(f"{chords_seen} distinct chords in the time rows, fewer than folds={folds}")

    predictors: dict[str, Predictor] = {
        "baseline": _baseline_time,
        "ridge": _ridge,
        "boosting": _boosting_for(seed),
    }
    time_report: dict[str, dict[str, Any]] = {}
    name: str
    for name in TIME_MODELS:
        oof: Floats = _out_of_fold(predictors[name], x_time, y_time, g_time, folds, seed)
        time_report[name] = {
            "mae_ms": round(float(mean_absolute_error(y_time, oof)), 1),
            "r2": round(float(r2_score(y_time, oof)), 6),
            "chord_mae_ms": _round(_chord_mae(y_time, oof, g_time), 1),
        }
    chosen: str = min(TIME_MODELS, key=lambda m: time_report[m]["mae_ms"]) if model == "auto" else model

    all_chords: tuple[int, ...] = allowed_chords(max_keys)
    usable: tuple[int, ...] = available_chords(max_keys, profile)
    x_usable: Floats = features_frame(usable).to_numpy(dtype=np.float64)
    time_pred: Floats = predictors[chosen](x_time, y_time, x_usable)

    y_miss: Floats = miss.astype(np.float64)
    miss_report: dict[str, Any] | None = None
    miss_model: str = "baseline"
    n_miss: int = int(miss.sum())
    if n_miss >= MIN_MISSES and len(miss) - n_miss >= MIN_MISSES:
        miss_predictors: dict[str, Predictor] = {"baseline": _baseline_miss, "logistic": _logistic}
        miss_report = {}
        for name in MISS_MODELS:
            oof_miss: Floats = _out_of_fold(miss_predictors[name], features, y_miss, chords, folds, seed)
            miss_report[name] = {
                "log_loss": round(float(log_loss(y_miss, oof_miss, labels=[0, 1])), 6),
                "brier": round(float(brier_score_loss(y_miss, oof_miss)), 6),
            }
        miss_model = (
            "logistic"
            if miss_report["logistic"]["log_loss"] < miss_report["baseline"]["log_loss"]
            else "baseline"
        )
        miss_report["chosen"] = miss_model
        miss_pred: Floats = miss_predictors[miss_model](features, y_miss, x_usable)
    else:
        miss_pred = _baseline_miss(features, y_miss, x_usable)

    time_of: dict[int, float] = {c: float(t) for c, t in zip(usable, time_pred, strict=True)}
    miss_of: dict[int, float] = {c: float(p) for c, p in zip(usable, miss_pred, strict=True)}
    rows: list[dict[str, Any]] = []
    chord: int
    for chord in all_chords:
        ok: bool = chord in time_of
        rows.append(
            {
                "chord": chord,
                "label": chord_label(chord),
                "keys": chord.bit_count(),
                "available": ok,
                "time_ms": round(time_of[chord], 1) if ok else None,
                "miss_prob": round(miss_of[chord], 6) if ok else None,
            }
        )
    sessions: list[dict[str, Any]] = _sessions(frame, column, max_ms)
    keyboard_obj: dict[str, str] | None = (
        None if keyboard is None else {"name": keyboard[0], "sha256": keyboard[1]}
    )
    ridge_all: Ridge = Ridge(alpha=1.0).fit(x_time, y_time)
    coefficients: dict[str, float] = {"intercept": round(float(ridge_all.intercept_), 6)}
    coef: float
    for name, coef in zip(FEATURE_NAMES, ridge_all.coef_, strict=True):
        coefficients[name] = round(float(coef), 6)
    prices: dict[str, Any] = {
        "format": PRICES_FORMAT,
        "version": PRICE_VERSION,
        "target": target,
        "model": chosen,
        "miss_model": miss_model,
        "max_keys": max_keys,
        "seed": seed,
        "keyboard": keyboard_obj,
        "available": len(usable),
        "unavailable": len(all_chords) - len(usable),
        "sessions": [s["session"] for s in sessions],
        "prices": rows,
    }
    report: dict[str, Any] = {
        "format": REPORT_FORMAT,
        "version": PRICE_VERSION,
        "target": target,
        "max_keys": max_keys,
        "seed": seed,
        "folds": folds,
        "max_ms": float(max_ms),
        "keyboard": keyboard_obj,
        "rows": len(frame),
        "time_rows": len(y_time),
        "misses": n_miss,
        "dropped_slow": dropped_slow,
        "chords_seen": chords_seen,
        "sessions": sessions,
        "time": time_report,
        "chosen": chosen,
        "ridge_coefficients": coefficients,
        "miss": miss_report,
        "suspect_chords": _suspects(frame),
        "features": list(FEATURE_NAMES),
    }
    return PriceFit(prices, report)

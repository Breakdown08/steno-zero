"""Surrogate data: features, data generation, metrics, linear baseline. No torch."""

import functools
import json
import math
import random
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy

from steno_zero.chords import N_CHORDS, N_KEYS
from steno_zero.evolve import EvolveParams, _eval_worker, _init_worker, evolve, random_table
from steno_zero.params import DEFAULT_MAX_KEYS, MAX_PIECE_LEN, PenaltyParams
from steno_zero.simulate import Score, evaluate
from steno_zero.table import Table

FEATURES: tuple[str, ...] = (
    *[f"k{i}" for i in range(N_KEYS)],
    "keys",
    "cost",
    "length",
    "uses",
    "neighbours",
    "one",
)
N_FEATURES: int = 16
DATA_FORMAT: str = "steno-zero/surrogate-data"
DATA_VERSION: int = 1
SOURCES: tuple[str, ...] = ("trajectory", "random")


class PieceCounts:
    def __init__(self, text: str) -> None:
        if text == "":
            raise ValueError("text must not be empty")
        self._text: str = text
        self._cache: dict[str, int] = {}

    def count(self, piece: str) -> int:
        found: int | None = self._cache.get(piece)
        if found is None:
            found = self._text.count(piece)
            self._cache[piece] = found
        return found

    @property
    def chars(self) -> int:
        return len(self._text)


@functools.cache
def _chord_static(costs: tuple[int, ...]) -> numpy.ndarray:
    """Per chord, 12 columns: ten key bits, keys / 10, cost / 1000. Row 0 is unused."""
    chords: numpy.ndarray = numpy.arange(N_CHORDS + 1)
    out: numpy.ndarray = numpy.zeros((N_CHORDS + 1, N_KEYS + 2), dtype=numpy.float64)
    bits: numpy.ndarray = (chords[:, None] >> numpy.arange(N_KEYS)[None, :]) & 1
    out[:, :N_KEYS] = bits
    out[:, N_KEYS] = bits.sum(axis=1) / N_KEYS
    out[:, N_KEYS + 1] = numpy.asarray(costs[: N_CHORDS + 1], dtype=numpy.float64) / 1000
    return out


_KEY_BITS: numpy.ndarray = 1 << numpy.arange(N_KEYS)


def table_features(table: Table, counts: PieceCounts, costs: Sequence[int], horizon: float) -> numpy.ndarray:
    entries: dict[str, int] = table.entries
    pieces: list[str] = list(entries)
    chords: numpy.ndarray = numpy.fromiter(entries.values(), dtype=numpy.int64, count=len(entries))
    static: numpy.ndarray = _chord_static(tuple(costs))
    out: numpy.ndarray = numpy.zeros((len(entries), N_FEATURES), dtype=numpy.float32)
    out[:, : N_KEYS + 2] = static[chords]
    out[:, 12] = (
        numpy.fromiter((len(p) for p in pieces), dtype=numpy.float64, count=len(pieces)) / MAX_PIECE_LEN
    )
    used: numpy.ndarray = numpy.fromiter(
        (counts.count(p) for p in pieces), dtype=numpy.float64, count=len(pieces)
    )
    out[:, 13] = numpy.log1p(horizon * used / counts.chars) / math.log1p(horizon)
    present: numpy.ndarray = numpy.zeros(N_CHORDS + 1, dtype=bool)
    present[chords] = True
    out[:, 14] = present[chords[:, None] ^ _KEY_BITS[None, :]].sum(axis=1) / N_KEYS
    out[:, 15] = 1.0
    return out


@dataclass(frozen=True)
class DataParams:
    seed_base: int = 1000
    seeds: int = 4
    population: int = 32
    generations: int = 300
    random: int = 500
    random_extra: int = 150
    max_keys: int = DEFAULT_MAX_KEYS

    def __post_init__(self) -> None:
        if self.seeds < 2:
            raise ValueError("seeds must be at least 2")
        EvolveParams(population=self.population, generations=self.generations, max_keys=self.max_keys)
        if self.generations < 0:
            raise ValueError("generations must not be negative")
        if self.random < 0:
            raise ValueError("random must not be negative")
        if self.random_extra < 0:
            raise ValueError("random_extra must not be negative")


@dataclass(frozen=True)
class DataRow:
    seed: int
    source: str
    generation: int | None
    total: float
    table: Table


def _trajectory(
    text: str,
    costs: Sequence[int],
    penalty: PenaltyParams,
    horizon: float,
    params: DataParams,
    seed: int,
    workers: int,
) -> list[DataRow]:
    traj: list[DataRow] = []

    def on_evaluated(generation: int, fresh: list[Table], scores: list[Score]) -> None:
        t: Table
        s: Score
        for t, s in zip(fresh, scores, strict=True):
            traj.append(DataRow(seed, "trajectory", generation, s.total, t))

    evolve(
        text,
        costs,
        penalty,
        horizon,
        EvolveParams(
            seed=seed, population=params.population, generations=params.generations, max_keys=params.max_keys
        ),
        workers,
        on_evaluated=on_evaluated,
    )
    return traj


def generate_data(
    text: str,
    costs: Sequence[int],
    penalty: PenaltyParams,
    horizon: float,
    params: DataParams,
    workers: int = 1,
) -> list[DataRow]:
    if workers < 1:
        raise ValueError("workers must be at least 1")
    rows: list[DataRow] = []
    seed: int
    for seed in range(params.seed_base, params.seed_base + params.seeds):
        traj: list[DataRow] = _trajectory(text, costs, penalty, horizon, params, seed, workers)
        rows.extend(traj)
        rng: random.Random = random.Random(f"surrogate-random-{seed}")
        tables: list[Table] = [
            random_table(text, rng, params.random_extra, params.max_keys) for _ in range(params.random)
        ]
        scores: list[Score]
        if workers == 1 or not tables:
            scores = [evaluate(text, t, costs, penalty, horizon) for t in tables]
        else:
            executor: Any
            with ProcessPoolExecutor(
                max_workers=workers, initializer=_init_worker, initargs=(text, costs, penalty, horizon)
            ) as executor:
                scores = list(executor.map(_eval_worker, tables, chunksize=8))
        rows.extend(DataRow(seed, "random", None, s.total, t) for t, s in zip(tables, scores, strict=True))
    return rows


def _dump(obj: dict[str, Any]) -> str:
    return json.dumps(obj, ensure_ascii=False)


def data_lines(header: dict[str, Any], rows: Sequence[DataRow]) -> str:
    lines: list[str] = [_dump(header)]
    r: DataRow
    for r in rows:
        lines.append(
            _dump(
                {
                    "type": "table",
                    "seed": r.seed,
                    "source": r.source,
                    "generation": r.generation,
                    "total": r.total,
                    "entries": [[p, c] for p, c in r.table.entries.items()],
                }
            )
        )
    return "\n".join(lines) + "\n"


def read_data(path: Path) -> tuple[dict[str, Any], list[DataRow]]:
    lines: list[str] = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip() != ""]
    try:
        header: Any = json.loads(lines[0]) if lines else None
        if (
            not isinstance(header, dict)
            or header.get("type") != "run"
            or header.get("format") != DATA_FORMAT
            or header.get("version") != DATA_VERSION
        ):
            raise ValueError(f"{path}: not a steno-zero surrogate data file, version {DATA_VERSION}")
        rows: list[DataRow] = []
        ln: str
        for ln in lines[1:]:
            obj: Any = json.loads(ln)
            if obj["type"] != "table" or obj["source"] not in SOURCES:
                raise ValueError("bad table line")
            rows.append(
                DataRow(
                    obj["seed"],
                    obj["source"],
                    obj["generation"],
                    float(obj["total"]),
                    Table({p: c for p, c in obj["entries"]}),
                )
            )
    except (KeyError, TypeError) as exc:
        raise ValueError(f"{path}: bad surrogate data: {exc!r}") from exc
    return header, rows


def _ranks(values: Sequence[float]) -> numpy.ndarray:
    arr: numpy.ndarray = numpy.asarray(values, dtype=numpy.float64)
    order: numpy.ndarray = numpy.argsort(arr, kind="stable")
    ranks: numpy.ndarray = numpy.empty(len(arr), dtype=numpy.float64)
    sorted_vals: numpy.ndarray = arr[order]
    i: int = 0
    n: int = len(arr)
    while i < n:
        j: int = i
        while j + 1 < n and sorted_vals[j + 1] == sorted_vals[i]:
            j += 1
        ranks[order[i : j + 1]] = (i + j) / 2
        i = j + 1
    return ranks


def spearman(a: Sequence[float], b: Sequence[float]) -> float | None:
    if len(a) != len(b):
        raise ValueError("vectors must have the same length")
    if len(a) < 2:
        raise ValueError("need at least 2 values")
    ra: numpy.ndarray = _ranks(a)
    rb: numpy.ndarray = _ranks(b)
    ra = ra - ra.mean()
    rb = rb - rb.mean()
    denom: float = float(numpy.sqrt((ra * ra).sum() * (rb * rb).sum()))
    if denom == 0.0:
        return None
    return float((ra * rb).sum() / denom)


def generation_spearman(rows: Sequence[DataRow], predicted: Sequence[float]) -> float | None:
    if len(rows) != len(predicted):
        raise ValueError("rows and predictions must have the same length")
    groups: dict[tuple[int, int | None], list[int]] = {}
    i: int
    r: DataRow
    for i, r in enumerate(rows):
        if r.source == "trajectory":
            groups.setdefault((r.seed, r.generation), []).append(i)
    values: list[float] = []
    idx: list[int]
    for idx in groups.values():
        if len(idx) < 3:
            continue
        rho: float | None = spearman([rows[k].total for k in idx], [predicted[k] for k in idx])
        if rho is not None:
            values.append(rho)
    return sum(values) / len(values) if values else None


def metrics(rows: Sequence[DataRow], predicted: Sequence[float]) -> dict[str, Any]:
    if len(rows) != len(predicted):
        raise ValueError("rows and predictions must have the same length")
    if not rows:
        return {"rows": 0, "spearman": None, "generation_spearman": None, "mae_s": None}
    totals: list[float] = [r.total for r in rows]
    return {
        "rows": len(rows),
        "spearman": spearman(totals, predicted) if len(rows) >= 2 else None,
        "generation_spearman": generation_spearman(rows, predicted),
        "mae_s": float(numpy.mean(numpy.abs(numpy.asarray(totals) - numpy.asarray(predicted)))),
    }


def _summed(
    rows: Sequence[DataRow], counts: PieceCounts, costs: Sequence[int], horizon: float
) -> numpy.ndarray:
    out: numpy.ndarray = numpy.zeros((len(rows), N_FEATURES + 1), dtype=numpy.float64)
    i: int
    r: DataRow
    for i, r in enumerate(rows):
        out[i, :N_FEATURES] = table_features(r.table, counts, costs, horizon).sum(axis=0, dtype=numpy.float64)
    out[:, N_FEATURES] = 1.0
    return out


def linear_baseline(
    train: Sequence[DataRow],
    holdout: Sequence[DataRow],
    counts: PieceCounts,
    costs: Sequence[int],
    horizon: float,
) -> list[float]:
    x: numpy.ndarray = _summed(train, counts, costs, horizon)
    y: numpy.ndarray = numpy.asarray([r.total for r in train], dtype=numpy.float64)
    coef: numpy.ndarray = numpy.linalg.lstsq(x, y, rcond=None)[0]
    pred: numpy.ndarray = _summed(holdout, counts, costs, horizon) @ coef
    return [float(v) for v in pred]


def split_by_seed(rows: Sequence[DataRow], holdout: int) -> tuple[list[DataRow], list[DataRow]]:
    seeds: list[int] = sorted({r.seed for r in rows})
    if holdout < 1 or holdout >= len(seeds):
        raise ValueError(f"holdout must be in 1..{len(seeds) - 1}")
    cut: set[int] = set(seeds[-holdout:])
    return [r for r in rows if r.seed not in cut], [r for r in rows if r.seed in cut]

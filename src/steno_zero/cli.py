"""Command line."""

import argparse
import dataclasses
import hashlib
import json
import os
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from types import ModuleType
from typing import IO, Any

from steno_zero.chords import allowed_chords, check_max_keys, chord_costs
from steno_zero.compare import RunStats, compare_runs, summarize
from steno_zero.corpus import fetch_corpus, load_corpus, split_corpus
from steno_zero.drill import (
    DRILL_BLOCKS,
    DRILL_SEED,
    DRILL_SIZE,
    DrillLog,
    drill_data,
    drill_strata,
    read_drill_js,
    read_drill_log,
    write_drill_js,
)
from steno_zero.evolve import (
    SAMPLE_CHARS,
    SAMPLE_CHUNKS,
    EvolveParams,
    EvolveResult,
    GenerationRecord,
    Screen,
    evolve,
    fitness_text,
)
from steno_zero.keyboard import (
    KEYBOARDS_DIR,
    CalibrationLog,
    KeyboardProfile,
    available_chords,
    build_profile,
    finger_blocked,
    keys_label,
    profile_json,
    read_calibration_log,
    read_profile,
)
from steno_zero.layout import LAYOUTS_DIR, Layout, read_layouts
from steno_zero.params import DEFAULT_HORIZON, DEFAULT_MAX_KEYS, CostParams, PenaltyParams
from steno_zero.plot import plot_log
from steno_zero.rival import rival_table
from steno_zero.setups import setups_data, write_setups_js
from steno_zero.simulate import Score, evaluate
from steno_zero.surrogate_data import DataParams, DataRow, data_lines, generate_data, read_data
from steno_zero.table import Table
from steno_zero.trainer import (
    EXAM_LIMIT,
    EXAM_SIZE,
    HOME_LIMIT,
    PHRASE_MAX_LEN,
    PHRASE_MIN_LEN,
    TrainerLog,
    TrainerStats,
    read_trainer_log,
    split_phrases,
    trainer_data,
    trainer_stats,
    write_data_js,
)

DEFAULT_SOURCES: Path = Path("data/corpus/sources.json")
DEFAULT_CORPUS: Path = Path("data/corpus/classics.txt")
DEFAULT_SURROGATE_DIR: Path = Path("runs/surrogate")
DEFAULT_OVERSAMPLE: int = 4
NO_TORCH: str = "torch is not installed; run `uv sync --extra surrogate`"


def _build_parser() -> argparse.ArgumentParser:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(prog="steno-zero")
    sub: Any = parser.add_subparsers(dest="command", required=True)

    corpus: argparse.ArgumentParser = sub.add_parser("corpus", help="corpus commands")
    corpus_sub: Any = corpus.add_subparsers(dest="corpus_command", required=True)
    fetch: argparse.ArgumentParser = corpus_sub.add_parser("fetch", help="download the pinned corpus")
    fetch.add_argument("--sources", type=Path, default=DEFAULT_SOURCES)
    fetch.add_argument("--out", type=Path, default=DEFAULT_CORPUS)

    rival: argparse.ArgumentParser = sub.add_parser("rival", help="build the frequency rival table")
    ev: argparse.ArgumentParser = sub.add_parser("evaluate", help="evaluate a table")
    ev.add_argument("--table", type=Path, required=True)
    p: argparse.ArgumentParser
    for p in (rival, ev):
        p.add_argument("--corpus", type=Path, default=None)
        p.add_argument("--horizon", type=float, default=DEFAULT_HORIZON)
        p.add_argument("--part", choices=["all", "train", "test"], default="all")
        p.add_argument("--confusion-s", type=float, default=PenaltyParams().confusion_s)
        p.add_argument("--max-keys", type=int, default=DEFAULT_MAX_KEYS)
    rival.add_argument("--out", type=Path, default=None)

    evo: argparse.ArgumentParser = sub.add_parser("evolve", help="evolve a table from scratch")
    evo.add_argument("--corpus", type=Path, default=None)
    evo.add_argument("--horizon", type=float, default=DEFAULT_HORIZON)
    evo.add_argument("--confusion-s", type=float, default=PenaltyParams().confusion_s)
    evo.add_argument("--max-keys", type=int, default=DEFAULT_MAX_KEYS)
    evo.add_argument("--seed", type=int, default=0)
    evo.add_argument("--population", type=int, default=EvolveParams().population)
    evo.add_argument("--generations", type=int, default=EvolveParams().generations)
    evo.add_argument("--sample-chars", type=int, default=SAMPLE_CHARS)
    evo.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    evo.add_argument("--surrogate", type=Path, default=None, metavar="MODEL")
    evo.add_argument("--oversample", type=int, default=None)
    evo.add_argument("--out", type=Path, default=None)

    plot: argparse.ArgumentParser = sub.add_parser("plot", help="plot the record log")
    plot.add_argument("--log", type=Path, required=True)
    plot.add_argument("--out", type=Path, default=None)

    trainer: argparse.ArgumentParser = sub.add_parser("trainer", help="browser trainer data and statistics")
    trainer_sub: Any = trainer.add_subparsers(dest="trainer_command", required=True)
    export: argparse.ArgumentParser = trainer_sub.add_parser("export", help="build docs/data.js")
    export.add_argument("--table", action="append", required=True, metavar="NAME=PATH")
    export.add_argument("--corpus", type=Path, default=None)
    export.add_argument("--min-len", type=int, default=PHRASE_MIN_LEN)
    export.add_argument("--max-len", type=int, default=PHRASE_MAX_LEN)
    export.add_argument("--home-limit", type=int, default=HOME_LIMIT)
    export.add_argument("--exam-limit", type=int, default=EXAM_LIMIT)
    export.add_argument("--exam-size", type=int, default=EXAM_SIZE)
    export.add_argument("--max-keys", type=int, default=DEFAULT_MAX_KEYS)
    export.add_argument("--out", type=Path, default=Path("docs/data.js"))
    stats: argparse.ArgumentParser = trainer_sub.add_parser("stats", help="statistics of exam logs")
    stats.add_argument("logs", type=Path, nargs="+", metavar="LOG")
    stats.add_argument("--out", type=Path, default=None)
    drill: argparse.ArgumentParser = trainer_sub.add_parser("drill", help="build docs/drill.js")
    drill.add_argument("--seed", type=int, default=DRILL_SEED)
    drill.add_argument("--blocks", type=int, default=DRILL_BLOCKS)
    drill.add_argument("--size", type=int, default=DRILL_SIZE)
    drill.add_argument("--max-keys", type=int, default=DEFAULT_MAX_KEYS)
    drill.add_argument("--out", type=Path, default=Path("docs/drill.js"))
    setups: argparse.ArgumentParser = trainer_sub.add_parser("setups", help="build docs/setups.js")
    setups.add_argument("--layouts", type=Path, default=LAYOUTS_DIR)
    setups.add_argument("--keyboards", type=Path, default=KEYBOARDS_DIR)
    setups.add_argument("--drill", type=Path, default=Path("docs/drill.js"))
    setups.add_argument("--out", type=Path, default=Path("docs/setups.js"))

    sur: argparse.ArgumentParser = sub.add_parser("surrogate", help="neural surrogate of the table score")
    sur_sub: Any = sur.add_subparsers(dest="surrogate_command", required=True)
    sdata: argparse.ArgumentParser = sur_sub.add_parser("data", help="write a training data set")
    sdata.add_argument("--corpus", type=Path, default=None)
    sdata.add_argument("--horizon", type=float, default=DEFAULT_HORIZON)
    sdata.add_argument("--confusion-s", type=float, default=PenaltyParams().confusion_s)
    sdata.add_argument("--max-keys", type=int, default=DEFAULT_MAX_KEYS)
    sdata.add_argument("--sample-chars", type=int, default=SAMPLE_CHARS)
    sdata.add_argument("--seed-base", type=int, default=DataParams().seed_base)
    sdata.add_argument("--seeds", type=int, default=DataParams().seeds)
    sdata.add_argument("--population", type=int, default=DataParams().population)
    sdata.add_argument("--generations", type=int, default=DataParams().generations)
    sdata.add_argument("--random", type=int, default=DataParams().random)
    sdata.add_argument("--random-extra", type=int, default=DataParams().random_extra)
    sdata.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    sdata.add_argument("--out", type=Path, default=DEFAULT_SURROGATE_DIR / "data.jsonl")
    strain: argparse.ArgumentParser = sur_sub.add_parser("train", help="train the surrogate on CPU")
    strain.add_argument("--data", type=Path, required=True)
    strain.add_argument("--corpus", type=Path, default=None)
    strain.add_argument("--seed", type=int, default=0)
    strain.add_argument("--epochs", type=int, default=30)
    strain.add_argument("--batch", type=int, default=256)
    strain.add_argument("--lr", type=float, default=1e-3)
    strain.add_argument("--hidden", type=int, default=64)
    strain.add_argument("--holdout", type=int, default=1)
    strain.add_argument("--out", type=Path, default=DEFAULT_SURROGATE_DIR / "model.pt")
    scmp: argparse.ArgumentParser = sur_sub.add_parser(
        "compare", help="evolution with and without the surrogate"
    )
    scmp.add_argument("--model", type=Path, required=True)
    scmp.add_argument("--corpus", type=Path, default=None)
    scmp.add_argument("--seed-base", type=int, default=0)
    scmp.add_argument("--seeds", type=int, default=3)
    scmp.add_argument("--population", type=int, default=EvolveParams().population)
    scmp.add_argument("--generations", type=int, default=EvolveParams().generations)
    scmp.add_argument("--oversample", type=int, default=DEFAULT_OVERSAMPLE)
    scmp.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    scmp.add_argument("--out", type=Path, default=DEFAULT_SURROGATE_DIR / "compare.json")

    keyboard: argparse.ArgumentParser = sub.add_parser("keyboard", help="keyboard calibration")
    keyboard_sub: Any = keyboard.add_subparsers(dest="keyboard_command", required=True)
    profile: argparse.ArgumentParser = keyboard_sub.add_parser("profile", help="build a keyboard profile")
    profile.add_argument("log", type=Path, metavar="LOG")
    profile.add_argument("--name", required=True)
    profile.add_argument("--out", type=Path, default=None)
    profile.add_argument("--max-keys", type=int, default=DEFAULT_MAX_KEYS)

    price: argparse.ArgumentParser = sub.add_parser("price", help="chord prices from measurements")
    price_sub: Any = price.add_subparsers(dest="price_command", required=True)
    pfit: argparse.ArgumentParser = price_sub.add_parser("fit", help="fit chord prices to drill logs")
    pfit.add_argument("logs", type=Path, nargs="+", metavar="LOG")
    pfit.add_argument("--keyboard", type=Path, default=None, metavar="PROFILE")
    pfit.add_argument("--layout", default=None, metavar="NAME")
    pfit.add_argument("--out", type=Path, default=Path("runs/price"))
    pfit.add_argument("--target", choices=["total", "motor"], default="total")
    pfit.add_argument("--model", choices=["auto", "baseline", "ridge", "boosting"], default="auto")
    pfit.add_argument("--folds", type=int, default=5)
    pfit.add_argument("--seed", type=int, default=0)
    pfit.add_argument("--skip-first", type=int, default=5)
    pfit.add_argument("--max-ms", type=float, default=5000.0)
    pfit.add_argument("--max-keys", type=int, default=DEFAULT_MAX_KEYS)
    return parser


def _read_text(corpus: Path | None, part: str) -> str:
    text: str
    if corpus is not None:
        text = load_corpus(corpus)
    else:
        if not DEFAULT_CORPUS.is_file():
            raise ValueError(f"{DEFAULT_CORPUS} not found; run `steno-zero corpus fetch` first")
        sources: dict[str, Any] = json.loads(DEFAULT_SOURCES.read_text(encoding="utf-8"))
        text = load_corpus(DEFAULT_CORPUS, sources.get("corpus_sha256"))
    if part == "all":
        return text
    train: str
    test: str
    train, test = split_corpus(text, 0.1)
    return train if part == "train" else test


def _check_table(table: Table, max_keys: int, name: str | None = None) -> None:
    over: list[str] = table.over_keys(max_keys)
    if not over:
        return
    entries: dict[str, int] = table.entries
    listed: str = ", ".join(f"{p!r} ({entries[p].bit_count()})" for p in over)
    where: str = f"table {name!r}" if name is not None else "table"
    raise ValueError(
        f"{where} has chords with more than {max_keys} keys: {listed}; use --max-keys to raise the limit"
    )


def _summary(score: Score, entries: int) -> str:
    return json.dumps(
        {
            "chars": score.chars,
            "chords": score.chords,
            "entries": entries,
            "t_char": score.t_char,
            "memory": score.memory,
            "confusion": score.confusion,
            "total": score.total,
        }
    )


def _dump(obj: dict[str, Any]) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _generation_row(rec: GenerationRecord) -> dict[str, Any]:
    return {"type": "generation", **dataclasses.asdict(rec)}


def _evolve_command(args: argparse.Namespace) -> int:
    params: EvolveParams = EvolveParams(
        seed=args.seed, population=args.population, generations=args.generations, max_keys=args.max_keys
    )
    if args.workers < 1:
        raise ValueError("workers must be at least 1")
    if args.surrogate is None and args.oversample is not None:
        raise ValueError("--oversample needs --surrogate")
    oversample: int = DEFAULT_OVERSAMPLE if args.oversample is None else args.oversample
    if args.surrogate is None:
        oversample = 1
    if oversample < 1:
        raise ValueError("--oversample must be at least 1")
    module: ModuleType | None = _surrogate_module() if args.surrogate is not None else None
    text: str = _read_text(args.corpus, "all")
    train: str
    test: str
    train, test = split_corpus(text, 0.1)
    fit: str = fitness_text(train, args.sample_chars, SAMPLE_CHUNKS)
    cost_params: CostParams = CostParams()
    penalty: PenaltyParams = PenaltyParams(confusion_s=args.confusion_s)
    costs: tuple[int, ...] = chord_costs(cost_params)
    horizon: float = args.horizon
    screen: Screen | None = None
    model_sha: str = ""
    if module is not None:
        model: Any = module.load_surrogate(args.surrogate, fit)
        module.check_compatible(
            model.meta,
            hashlib.sha256(fit.encode("utf-8")).hexdigest(),
            horizon,
            params.max_keys,
            _json_like(dataclasses.asdict(cost_params)),
            _json_like(dataclasses.asdict(penalty)),
        )
        model_sha = hashlib.sha256(args.surrogate.read_bytes()).hexdigest()
        screen = model.predict
    rival: Table = rival_table(train, costs, params.max_keys)
    rival_total: float = evaluate(fit, rival, costs, penalty, horizon).total
    out: Path = args.out if args.out is not None else Path("runs") / f"seed-{args.seed}"
    out.mkdir(parents=True, exist_ok=True)
    run_row: dict[str, Any] = {
        "type": "run",
        "format": "steno-zero/evolve-log",
        "version": 3 if module is None else 4,
        **dataclasses.asdict(params),
        "horizon": horizon,
        "sample_chars": args.sample_chars,
        "sample_chunks": SAMPLE_CHUNKS,
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "train_chars": len(train),
        "test_chars": len(test),
        "fit_chars": len(fit),
        "cost_params": dataclasses.asdict(cost_params),
        "penalty_params": dataclasses.asdict(penalty),
        "rival_total": rival_total,
    }
    if module is not None:
        run_row["surrogate_sha256"] = model_sha
        run_row["oversample"] = oversample
    start: float = time.monotonic()

    def on_generation(rec: GenerationRecord) -> None:
        log.write(_dump(_generation_row(rec)) + "\n")
        log.flush()
        print(
            f"gen {rec.generation} best {rec.best_total:.1f} entries {rec.entries} "
            f"time {time.monotonic() - start:.1f}s",
            file=sys.stderr,
        )

    result: EvolveResult
    log: IO[str]
    with (out / "log.jsonl").open("w", encoding="utf-8", newline="\n") as log:
        log.write(_dump(run_row) + "\n")
        log.flush()
        result = evolve(
            fit, costs, penalty, horizon, params, args.workers, on_generation,
            screen=screen, oversample=oversample,
        )  # fmt: skip
        best: Table = result.best
        totals: dict[str, float] = {}
        name: str
        part: str
        for name, part in (("train", train), ("test", test)):
            totals[name] = evaluate(part, best, costs, penalty, horizon).total
            totals["rival_" + name] = evaluate(part, rival, costs, penalty, horizon).total
        result_row: dict[str, Any] = {
            "type": "result",
            "best_total": result.score.total,
            "rival_total": rival_total,
            "train_total": totals["train"],
            "rival_train_total": totals["rival_train"],
            "test_total": totals["test"],
            "rival_test_total": totals["rival_test"],
            "entries": len(best),
        }
        log.write(_dump(result_row) + "\n")
    (out / "best.json").write_text(best.to_json(), encoding="utf-8")
    print(_dump(result_row))
    return 0


def _surrogate_module() -> ModuleType:
    """Import the torch part lazily; a missing torch becomes a plain error message."""
    try:
        import steno_zero.surrogate as module
    except ImportError as exc:
        raise ValueError(NO_TORCH) from exc
    import torch

    torch.set_num_threads(1)
    return module


def _json_like(data: dict[str, Any]) -> dict[str, Any]:
    """What a dataclass dict looks like after a trip through JSON (tuples become lists)."""
    out: dict[str, Any] = json.loads(json.dumps(data))
    return out


def _surrogate_data_command(args: argparse.Namespace) -> int:
    if args.workers < 1:
        raise ValueError("workers must be at least 1")
    params: DataParams = DataParams(
        seed_base=args.seed_base,
        seeds=args.seeds,
        population=args.population,
        generations=args.generations,
        random=args.random,
        random_extra=args.random_extra,
        max_keys=args.max_keys,
    )
    text: str = _read_text(args.corpus, "all")
    train: str = split_corpus(text, 0.1)[0]
    fit: str = fitness_text(train, args.sample_chars, SAMPLE_CHUNKS)
    cost_params: CostParams = CostParams()
    penalty: PenaltyParams = PenaltyParams(confusion_s=args.confusion_s)
    started: float = time.monotonic()
    rows: list[DataRow] = generate_data(
        fit, chord_costs(cost_params), penalty, args.horizon, params, args.workers
    )
    header: dict[str, Any] = {
        "type": "run",
        "format": "steno-zero/surrogate-data",
        "version": 1,
        "seed_base": params.seed_base,
        "seeds": params.seeds,
        "population": params.population,
        "generations": params.generations,
        "random": params.random,
        "random_extra": params.random_extra,
        "max_keys": params.max_keys,
        "horizon": args.horizon,
        "sample_chars": args.sample_chars,
        "sample_chunks": SAMPLE_CHUNKS,
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "fit_sha256": hashlib.sha256(fit.encode("utf-8")).hexdigest(),
        "fit_chars": len(fit),
        "cost_params": dataclasses.asdict(cost_params),
        "penalty_params": dataclasses.asdict(penalty),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    handle: IO[str]
    with args.out.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(data_lines(header, rows))
    print(f"{len(rows)} rows in {time.monotonic() - started:.1f}s", file=sys.stderr)
    trajectory: int = sum(1 for r in rows if r.source == "trajectory")
    print(
        _dump(
            {
                "rows": len(rows),
                "trajectory": trajectory,
                "random": len(rows) - trajectory,
                "seeds": list(range(params.seed_base, params.seed_base + params.seeds)),
                "out": str(args.out),
            }
        )
    )
    return 0


def _surrogate_train_command(args: argparse.Namespace) -> int:
    module: ModuleType = _surrogate_module()
    header: dict[str, Any]
    rows: list[DataRow]
    header, rows = read_data(args.data)
    text: str = _read_text(args.corpus, "all")
    train: str = split_corpus(text, 0.1)[0]
    fit: str = fitness_text(train, header["sample_chars"], header["sample_chunks"])
    params: Any = module.TrainParams(
        seed=args.seed,
        epochs=args.epochs,
        batch=args.batch,
        lr=args.lr,
        hidden=args.hidden,
        holdout=args.holdout,
    )
    model: Any
    report: dict[str, Any]
    model, report = module.train_surrogate(header, rows, fit, params)
    module.save_surrogate(model, args.out)
    report["model_sha256"] = hashlib.sha256(args.out.read_bytes()).hexdigest()
    args.out.with_suffix(".json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        _dump(
            {
                "rows_train": report["rows_train"],
                "rows_holdout": report["rows_holdout"],
                "spearman": report["holdout"]["all"]["spearman"],
                "generation_spearman": report["holdout"]["all"]["generation_spearman"],
                "linear_generation_spearman": report["linear"]["all"]["generation_spearman"],
                "train_s": report["train_s"],
                "out": str(args.out),
            }
        )
    )
    return 0


def _surrogate_compare_command(args: argparse.Namespace) -> int:
    module: ModuleType = _surrogate_module()
    if args.workers < 1:
        raise ValueError("workers must be at least 1")
    if args.seeds < 1:
        raise ValueError("seeds must be at least 1")
    text: str = _read_text(args.corpus, "all")
    train: str = split_corpus(text, 0.1)[0]
    # the sample size comes out of the model file itself, which needs the sample to be checked
    meta: dict[str, Any] = module.read_meta(args.model)
    fit: str = fitness_text(train, meta["sample_chars"], meta["sample_chunks"])
    model: Any = module.load_surrogate(args.model, fit)
    meta = model.meta
    penalty: PenaltyParams = PenaltyParams(**meta["penalty_params"])
    costs: tuple[int, ...] = chord_costs(
        CostParams(
            base_ms=meta["cost_params"]["base_ms"],
            extra_key_ms=meta["cost_params"]["extra_key_ms"],
            finger_ms=tuple(meta["cost_params"]["finger_ms"]),
        )
    )
    params: EvolveParams = EvolveParams(
        population=args.population, generations=args.generations, max_keys=meta["max_keys"]
    )
    seeds: list[int] = list(range(args.seed_base, args.seed_base + args.seeds))
    runs: list[RunStats] = compare_runs(
        fit, costs, penalty, meta["horizon"], params, seeds, args.oversample, model.predict, args.workers
    )
    summary: dict[str, Any] = summarize(runs)
    report: dict[str, Any] = {
        "format": "steno-zero/surrogate-compare",
        "version": 1,
        "model": {"path": str(args.model), "sha256": hashlib.sha256(args.model.read_bytes()).hexdigest()},
        "params": {
            "seeds": seeds,
            "population": params.population,
            "generations": params.generations,
            "elite": params.elite,
            "oversample": args.oversample,
            "workers": args.workers,
            "max_keys": meta["max_keys"],
            "horizon": meta["horizon"],
            "sample_chars": meta["sample_chars"],
            "fit_sha256": meta["fit_sha256"],
        },
        "runs": [dataclasses.asdict(r) for r in runs],
        "summary": summary,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(_dump(summary))
    return 0


def _plot_command(args: argparse.Namespace) -> int:
    out: Path = args.out if args.out is not None else args.log.with_name("records.png")
    plot_log(args.log, out)
    print(out)
    return 0


def _trainer_export(args: argparse.Namespace) -> int:
    check_max_keys(args.max_keys)
    tables: list[tuple[str, Table]] = []
    spec: str
    for spec in args.table:
        name: str
        sep: str
        path: str
        name, sep, path = spec.partition("=")
        if sep == "":
            raise ValueError(f"--table {spec!r}: expected NAME=PATH")
        table: Table = Table.from_json(Path(path).read_text(encoding="utf-8"))
        _check_table(table, args.max_keys, name)
        tables.append((name, table))
    text: str = _read_text(args.corpus, "all")
    home: list[str]
    exam: list[str]
    home, exam = split_phrases(text, args.min_len, args.max_len, args.home_limit, args.exam_limit)
    write_data_js(trainer_data(tables, home, exam, args.exam_size), args.out)
    print(
        _dump(
            {
                "out": str(args.out),
                "phrases": len(home),
                "exam_phrases": len(exam),
                "tables": [n for n, _ in tables],
            }
        )
    )
    return 0


def _trainer_stats(args: argparse.Namespace) -> int:
    logs: list[TrainerLog] = [read_trainer_log(p.read_text(encoding="utf-8")) for p in args.logs]
    result: TrainerStats = trainer_stats(logs)
    summary: dict[str, Any] = {
        "sessions": len(result.sessions),
        "attempts": result.attempts,
        "correct": result.correct,
        "neighbour_misses": result.neighbour_misses,
        "other_misses": result.other_misses,
        "slip_prob": result.slip_prob,
        "median_ms": result.median_ms,
    }
    rows: list[dict[str, Any]] = [dataclasses.asdict(s) for s in result.sessions]
    row: dict[str, Any]
    for row in rows:
        print(_dump(row))
    print(_dump(summary))
    if args.out is not None:
        chords: list[dict[str, Any]] = [
            {**dataclasses.asdict(c), "typed": [list(t) for t in c.typed]} for c in result.chords
        ]
        full: dict[str, Any] = {**summary, "sessions": rows, "chords": chords}
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(full, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


def _trainer_drill(args: argparse.Namespace) -> int:
    data: dict[str, Any] = drill_data(args.seed, args.blocks, args.size, args.max_keys)
    write_drill_js(data, args.out)
    print(
        _dump(
            {
                "out": str(args.out),
                "seed": args.seed,
                "blocks": args.blocks,
                "size": args.size,
                "max_keys": args.max_keys,
                "available": len(allowed_chords(args.max_keys)),
                "chords": len({c for block in data["blocks"] for c in block}),
                "strata": len(drill_strata(args.max_keys)),
            }
        )
    )
    return 0


def _trainer_setups(args: argparse.Namespace) -> int:
    if not args.layouts.is_dir():
        raise ValueError(f"{args.layouts}: not a folder of layouts")
    layouts: tuple[Layout, ...] = read_layouts(args.layouts)
    profiles: list[KeyboardProfile] = []
    if args.keyboards.is_dir():
        path: Path
        for path in sorted(args.keyboards.glob("*.json")):
            profiles.append(_read_with_name(path, read_profile))
    try:
        drill: dict[str, Any] = read_drill_js(args.drill)
    except ValueError as exc:
        raise ValueError(f"{args.drill}: {exc}") from exc
    data: dict[str, Any] = setups_data(layouts, profiles, drill)
    write_setups_js(data, args.out)
    print(_dump({"out": str(args.out), "setups": [x["name"] for x in data["setups"]]}))
    return 0


def _read_with_name[T](path: Path, read: Callable[[str], T]) -> T:
    try:
        return read(path.read_text(encoding="utf-8"))
    except OSError:
        raise
    except ValueError as exc:
        raise ValueError(f"{path}: {exc}") from exc


def _keyboard_command(args: argparse.Namespace) -> int:
    log: CalibrationLog = _read_with_name(args.log, read_calibration_log)
    profile: KeyboardProfile = build_profile(log, args.name)
    check_max_keys(args.max_keys)
    out: Path = args.out if args.out is not None else KEYBOARDS_DIR / f"{args.name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(profile_json(profile), encoding="utf-8", newline="\n")
    print(
        _dump(
            {
                "out": str(out),
                "name": profile.name,
                "keys": list(profile.keys),
                "blocked": [keys_label(b.keys) for b in profile.blocked],
                "unclear": [keys_label(b.keys) for b in profile.blocked if b.unclear],
                "available": len(available_chords(args.max_keys, finger_blocked(profile, log.layout))),
            }
        )
    )
    return 0


def _price_command(args: argparse.Namespace) -> int:
    from steno_zero.price import PriceFit, fit_prices, presentations_frame

    logs: list[DrillLog] = [_read_with_name(p, read_drill_log) for p in args.logs]
    if args.layout is not None:
        logs = [x for x in logs if x.layout.name == args.layout]
        if not logs:
            raise ValueError(f"no drill logs of the layout {args.layout!r}")
    counts: dict[str, int] = {}
    log: DrillLog
    for log in sorted(logs, key=lambda x: x.layout.name):
        counts[log.layout.name] = counts.get(log.layout.name, 0) + 1
    if len(counts) > 1:
        listed: str = ", ".join(f"{n} ({k} sessions)" for n, k in counts.items())
        print(f"warning: mixing drill logs of {len(counts)} layouts: {listed}", file=sys.stderr)
    profile: KeyboardProfile | None = None
    if args.keyboard is not None:
        profile = _read_with_name(args.keyboard, read_profile)
    frame: Any = presentations_frame(logs, args.skip_first)
    result: PriceFit = fit_prices(
        frame, args.target, args.model, args.max_keys, args.folds, args.seed, args.max_ms, profile
    )
    args.out.mkdir(parents=True, exist_ok=True)
    name: str
    obj: dict[str, Any]
    for name, obj in (("prices.json", result.prices), ("report.json", result.report)):
        text: str = json.dumps(obj, ensure_ascii=False, indent=1) + "\n"
        (args.out / name).write_text(text, encoding="utf-8", newline="\n")
    time: dict[str, dict[str, Any]] = result.report["time"]
    print(
        _dump(
            {
                "out": str(args.out),
                "rows": result.report["rows"],
                "time_rows": result.report["time_rows"],
                "chords_seen": result.report["chords_seen"],
                "chosen": result.report["chosen"],
                "mae_ms": {m: time[m]["mae_ms"] for m in time},
                "miss_model": result.prices["miss_model"],
                "keyboard": None if profile is None else profile.name,
                "layouts": result.prices["layouts"],
                "suspects": len(result.report["suspect_chords"]),
            }
        )
    )
    return 0


def _run(args: argparse.Namespace) -> int:
    if args.command == "corpus":
        print(fetch_corpus(args.sources, args.out))
        return 0
    if args.command == "evolve":
        return _evolve_command(args)
    if args.command == "plot":
        return _plot_command(args)
    if args.command == "surrogate":
        if args.surrogate_command == "data":
            return _surrogate_data_command(args)
        if args.surrogate_command == "train":
            return _surrogate_train_command(args)
        return _surrogate_compare_command(args)
    if args.command == "trainer":
        if args.trainer_command == "drill":
            return _trainer_drill(args)
        if args.trainer_command == "setups":
            return _trainer_setups(args)
        return _trainer_export(args) if args.trainer_command == "export" else _trainer_stats(args)
    if args.command == "keyboard":
        return _keyboard_command(args)
    if args.command == "price":
        return _price_command(args)
    check_max_keys(args.max_keys)
    table: Table
    if args.command == "evaluate":
        table = Table.from_json(args.table.read_text(encoding="utf-8"))
        _check_table(table, args.max_keys)
    text: str = _read_text(args.corpus, args.part)
    costs: tuple[int, ...] = chord_costs(CostParams())
    if args.command == "rival":
        table = rival_table(text, costs, args.max_keys)
        if args.out is not None:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(table.to_json(), encoding="utf-8")
    score: Score = evaluate(text, table, costs, PenaltyParams(confusion_s=args.confusion_s), args.horizon)
    print(_summary(score, len(table)))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args: argparse.Namespace = _build_parser().parse_args(argv)
    try:
        return _run(args)
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

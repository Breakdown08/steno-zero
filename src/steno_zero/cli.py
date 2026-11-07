"""Command line."""

import argparse
import dataclasses
import hashlib
import json
import os
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import IO, Any

from steno_zero.chords import chord_costs
from steno_zero.corpus import fetch_corpus, load_corpus, split_corpus
from steno_zero.evolve import (
    SAMPLE_CHARS,
    SAMPLE_CHUNKS,
    EvolveParams,
    EvolveResult,
    GenerationRecord,
    evolve,
    fitness_text,
)
from steno_zero.params import DEFAULT_HORIZON, CostParams, PenaltyParams
from steno_zero.plot import plot_log
from steno_zero.rival import rival_table
from steno_zero.simulate import Score, evaluate
from steno_zero.table import Table

DEFAULT_SOURCES: Path = Path("data/corpus/sources.json")
DEFAULT_CORPUS: Path = Path("data/corpus/classics.txt")


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
    rival.add_argument("--out", type=Path, default=None)

    evo: argparse.ArgumentParser = sub.add_parser("evolve", help="evolve a table from scratch")
    evo.add_argument("--corpus", type=Path, default=None)
    evo.add_argument("--horizon", type=float, default=DEFAULT_HORIZON)
    evo.add_argument("--confusion-s", type=float, default=PenaltyParams().confusion_s)
    evo.add_argument("--seed", type=int, default=0)
    evo.add_argument("--population", type=int, default=EvolveParams().population)
    evo.add_argument("--generations", type=int, default=EvolveParams().generations)
    evo.add_argument("--sample-chars", type=int, default=SAMPLE_CHARS)
    evo.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    evo.add_argument("--out", type=Path, default=None)

    plot: argparse.ArgumentParser = sub.add_parser("plot", help="plot the record log")
    plot.add_argument("--log", type=Path, required=True)
    plot.add_argument("--out", type=Path, default=None)
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
        seed=args.seed, population=args.population, generations=args.generations
    )
    if args.workers < 1:
        raise ValueError("workers must be at least 1")
    text: str = _read_text(args.corpus, "all")
    train: str
    test: str
    train, test = split_corpus(text, 0.1)
    fit: str = fitness_text(train, args.sample_chars, SAMPLE_CHUNKS)
    cost_params: CostParams = CostParams()
    penalty: PenaltyParams = PenaltyParams(confusion_s=args.confusion_s)
    costs: tuple[int, ...] = chord_costs(cost_params)
    horizon: float = args.horizon
    rival: Table = rival_table(train, costs)
    rival_total: float = evaluate(fit, rival, costs, penalty, horizon).total
    out: Path = args.out if args.out is not None else Path("runs") / f"seed-{args.seed}"
    out.mkdir(parents=True, exist_ok=True)
    run_row: dict[str, Any] = {
        "type": "run",
        "format": "steno-zero/evolve-log",
        "version": 2,
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
        result = evolve(fit, costs, penalty, horizon, params, args.workers, on_generation)
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


def _plot_command(args: argparse.Namespace) -> int:
    out: Path = args.out if args.out is not None else args.log.with_name("records.png")
    plot_log(args.log, out)
    print(out)
    return 0


def _run(args: argparse.Namespace) -> int:
    if args.command == "corpus":
        print(fetch_corpus(args.sources, args.out))
        return 0
    if args.command == "evolve":
        return _evolve_command(args)
    if args.command == "plot":
        return _plot_command(args)
    text: str = _read_text(args.corpus, args.part)
    costs: tuple[int, ...] = chord_costs(CostParams())
    table: Table
    if args.command == "rival":
        table = rival_table(text, costs)
        if args.out is not None:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(table.to_json(), encoding="utf-8")
    else:
        table = Table.from_json(args.table.read_text(encoding="utf-8"))
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

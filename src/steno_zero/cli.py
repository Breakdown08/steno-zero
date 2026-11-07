"""Command line."""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from steno_zero.chords import chord_costs
from steno_zero.corpus import fetch_corpus, load_corpus, split_corpus
from steno_zero.params import DEFAULT_HORIZON, CostParams, PenaltyParams
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
    rival.add_argument("--out", type=Path, default=None)
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
            "total": score.total,
        }
    )


def _run(args: argparse.Namespace) -> int:
    if args.command == "corpus":
        print(fetch_corpus(args.sources, args.out))
        return 0
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
    score: Score = evaluate(text, table, costs, PenaltyParams(), args.horizon)
    print(_summary(score, len(table)))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args: argparse.Namespace = _build_parser().parse_args(argv)
    try:
        return _run(args)
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

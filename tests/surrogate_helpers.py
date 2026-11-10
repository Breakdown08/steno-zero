"""Shared helpers for the surrogate tests."""

import contextlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from steno_zero.cli import main
from steno_zero.corpus import split_corpus
from steno_zero.params import PenaltyParams
from steno_zero.surrogate_data import DataParams, DataRow, generate_data, read_data
from tests.helpers import FRAGMENT_PATH, ROOT, costs, fragment

HORIZON: float = 1_000_000.0
SMALL: DataParams = DataParams(
    seed_base=1000, seeds=2, population=6, generations=3, random=5, random_extra=10
)
DATA_ARGS: list[str] = [
    "--sample-chars", "0", "--seeds", "2", "--population", "6", "--generations", "3",
    "--random", "5", "--random-extra", "10",
]  # fmt: skip
HEADER_KEYS: list[str] = [
    "type", "format", "version", "seed_base", "seeds", "population", "generations", "random",
    "random_extra", "max_keys", "horizon", "sample_chars", "sample_chunks", "text_sha256", "fit_sha256",
    "fit_chars", "cost_params", "penalty_params",
]  # fmt: skip
CODE: str = "import sys; from steno_zero.cli import main; raise SystemExit(main(sys.argv[1:]))"


def train_text() -> str:
    """The text the CLI fits on with --sample-chars 0: the train part of the fragment."""
    return split_corpus(fragment(), 0.1)[0]


def small_rows(workers: int = 1) -> list[DataRow]:
    return generate_data(train_text(), costs(), PenaltyParams(), HORIZON, SMALL, workers)


def run_main(argv: list[str]) -> tuple[int, str, str]:
    out: io.StringIO = io.StringIO()
    err: io.StringIO = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code: int = main(argv)
    return code, out.getvalue(), err.getvalue()


def data_command(out: Path, workers: str = "1") -> list[str]:
    return [
        "surrogate", "data", "--corpus", str(FRAGMENT_PATH), *DATA_ARGS, "--workers", workers,
        "--out", str(out),
    ]  # fmt: skip


def run_subprocess(argv: list[str], hashseed: str = "0") -> subprocess.CompletedProcess[bytes]:
    env: dict[str, str] = {**os.environ, "PYTHONHASHSEED": hashseed}
    return subprocess.run([sys.executable, "-c", CODE, *argv], cwd=ROOT, env=env, capture_output=True)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines()]


def cli_data(out: Path, *extra: str) -> tuple[dict[str, Any], list[DataRow]]:
    """Write a data file through the CLI (small sizes unless overridden) and read it back."""
    args: list[str] = [
        "surrogate", "data", "--corpus", str(FRAGMENT_PATH), "--sample-chars", "0", "--workers", "1",
        *(extra or ("--seeds", "2", "--population", "6", "--generations", "3", "--random", "5",
                    "--random-extra", "10")),
        "--out", str(out),
    ]  # fmt: skip
    code: int
    _: str
    err: str
    code, _, err = run_main(args)
    assert code == 0, err
    return read_data(out)

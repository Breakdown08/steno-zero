"""Checks 26-29, 32-34: evolve and plot commands, the log."""

import contextlib
import dataclasses
import hashlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from steno_zero.cli import main
from steno_zero.corpus import split_corpus
from steno_zero.params import CostParams, PenaltyParams
from steno_zero.plot import plot_log, read_log
from steno_zero.table import Table
from tests.helpers import FRAGMENT_PATH, ROOT, fragment

RUN_KEYS: list[str] = [
    "type", "format", "version", "seed", "population", "generations", "elite", "tournament",
    "init_extra", "max_mutations", "max_keys", "horizon", "sample_chars", "sample_chunks", "text_sha256",
    "train_chars", "test_chars", "fit_chars", "cost_params", "penalty_params", "rival_total",
]  # fmt: skip
GEN_KEYS: list[str] = [
    "type", "generation", "best_total", "gen_best_total", "mean_total", "entries", "t_char", "memory",
    "confusion", "record", "evaluations",
]  # fmt: skip
RESULT_KEYS: list[str] = [
    "type", "best_total", "rival_total", "train_total", "rival_train_total", "test_total",
    "rival_test_total", "entries",
]  # fmt: skip
PNG: bytes = b"\x89PNG\r\n\x1a\n"


def args_for(out: Path, *extra: str) -> list[str]:
    return [
        "evolve", "--corpus", str(FRAGMENT_PATH), "--population", "8", "--generations", "5",
        "--workers", "1", "--out", str(out), *extra,
    ]  # fmt: skip


def run_main(argv: list[str]) -> tuple[int, str, str]:
    out: io.StringIO = io.StringIO()
    err: io.StringIO = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code: int = main(argv)
    return code, out.getvalue(), err.getvalue()


@pytest.fixture(scope="module")
def evolved(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, int, str]:
    out: Path = tmp_path_factory.mktemp("run") / "r"
    code: int
    stdout: str
    _: str
    code, stdout, _ = run_main(args_for(out))
    return out, code, stdout


def log_lines(out: Path) -> list[dict[str, Any]]:
    lines: list[str] = (out / "log.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(ln) for ln in lines]


def test_log_structure(evolved: tuple[Path, int, str]) -> None:
    out: Path
    code: int
    _: str
    out, code, _ = evolved
    assert code == 0
    rows: list[dict[str, Any]] = log_lines(out)
    assert len(rows) == 8
    run: dict[str, Any] = rows[0]
    assert run["type"] == "run"
    assert list(run) == RUN_KEYS
    gens: list[dict[str, Any]] = rows[1:7]
    assert [g["generation"] for g in gens] == list(range(6))
    g: dict[str, Any]
    for g in gens:
        assert g["type"] == "generation"
        assert list(g) == GEN_KEYS
    result: dict[str, Any] = rows[7]
    assert result["type"] == "result"
    assert list(result) == RESULT_KEYS
    assert run["seed"] == 0
    assert run["population"] == 8
    assert run["generations"] == 5
    assert run["fit_chars"] == run["train_chars"]
    assert run["train_chars"] + run["test_chars"] == len(fragment())


def test_log_run_row_content(evolved: tuple[Path, int, str]) -> None:
    run: dict[str, Any] = log_lines(evolved[0])[0]
    assert run["format"] == "steno-zero/evolve-log"
    assert run["version"] == 3
    assert run["text_sha256"] == hashlib.sha256(fragment().encode("utf-8")).hexdigest()
    train: str
    test: str
    train, test = split_corpus(fragment(), 0.1)
    assert run["train_chars"] == len(train)
    assert run["test_chars"] == len(test)
    assert run["cost_params"] == json.loads(json.dumps(dataclasses.asdict(CostParams())))
    assert run["penalty_params"] == dataclasses.asdict(PenaltyParams())
    rows: list[dict[str, Any]] = log_lines(evolved[0])
    assert rows[-1]["best_total"] == rows[-2]["best_total"]
    assert rows[-1]["rival_total"] == run["rival_total"]


def test_log_format_on_disk(evolved: tuple[Path, int, str]) -> None:
    raw: str = (evolved[0] / "log.jsonl").read_text(encoding="utf-8")
    assert raw.endswith("\n")
    ln: str
    for ln in raw.splitlines():
        assert ln == json.dumps(json.loads(ln), ensure_ascii=False)
    assert "workers" not in raw


def test_best_json_and_stdout(evolved: tuple[Path, int, str], capsys: pytest.CaptureFixture[str]) -> None:
    out: Path
    stdout: str
    _: int
    out, _, stdout = evolved
    result: dict[str, Any] = log_lines(out)[-1]
    best: Path = out / "best.json"
    assert len(Table.from_json(best.read_text(encoding="utf-8"))) == result["entries"]
    last: str = (out / "log.jsonl").read_text(encoding="utf-8").splitlines()[-1]
    assert stdout.rstrip("\n").splitlines()[-1] == last
    code: int = main(["evaluate", "--table", str(best), "--corpus", str(FRAGMENT_PATH), "--part", "train"])
    assert code == 0
    ev: dict[str, Any] = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert ev["total"] == result["train_total"]


def subprocess_evolve(out: Path, hashseed: str, workers: str, seed: str = "0") -> None:
    code: str = "import sys; from steno_zero.cli import main; raise SystemExit(main(sys.argv[1:]))"
    env: dict[str, str] = {**os.environ, "PYTHONHASHSEED": hashseed}
    proc: subprocess.CompletedProcess[bytes] = subprocess.run(
        [sys.executable, "-c", code, "evolve", "--corpus", str(FRAGMENT_PATH), "--population", "8",
         "--generations", "5", "--seed", seed, "--workers", workers, "--out", str(out)],
        cwd=ROOT, env=env, capture_output=True,
    )  # fmt: skip
    assert proc.returncode == 0, proc.stderr.decode()


def test_byte_reproducibility(tmp_path: Path) -> None:
    a: Path = tmp_path / "a"
    b: Path = tmp_path / "b"
    c: Path = tmp_path / "c"
    subprocess_evolve(a, "0", "1")
    subprocess_evolve(b, "1", "1")
    subprocess_evolve(c, "2", "2")
    name: str
    for name in ("log.jsonl", "best.json"):
        data: bytes = (a / name).read_bytes()
        assert data != b""
        assert (b / name).read_bytes() == data
        assert (c / name).read_bytes() == data


def test_seed_changes_log(evolved: tuple[Path, int, str], tmp_path: Path) -> None:
    code: int
    _: str
    code, _, _ = run_main(args_for(tmp_path / "s1", "--seed", "1"))
    assert code == 0
    assert (tmp_path / "s1" / "log.jsonl").read_bytes() != (evolved[0] / "log.jsonl").read_bytes()


def test_evolve_errors(tmp_path: Path) -> None:
    code: int
    err: str
    _: str
    code, _, err = run_main(args_for(tmp_path / "p", "--population", "1"))
    assert code == 1
    assert err.strip() != ""
    code, _, err = run_main(args_for(tmp_path / "w", "--workers", "0"))
    assert code == 1
    assert err.strip() != ""
    code, _, err = run_main(["evolve", "--corpus", str(tmp_path / "нет.txt"), "--out", str(tmp_path / "m")])
    assert code == 1
    assert err.strip() != ""


# plot


def test_plot_default_and_custom_out(evolved: tuple[Path, int, str], tmp_path: Path) -> None:
    log: Path = evolved[0] / "log.jsonl"
    code: int
    stdout: str
    _: str
    code, stdout, _ = run_main(["plot", "--log", str(log)])
    png: Path = evolved[0] / "records.png"
    assert code == 0
    assert png.read_bytes()[:8] == PNG
    assert str(png) in stdout
    custom: Path = tmp_path / "sub" / "x.png"
    code, stdout, _ = run_main(["plot", "--log", str(log), "--out", str(custom)])
    assert code == 0
    assert custom.read_bytes()[:8] == PNG
    assert str(custom) in stdout


def run_row() -> dict[str, Any]:
    return {
        "type": "run", "format": "steno-zero/evolve-log", "version": 1, "seed": 3, "population": 8,
        "generations": 2, "elite": 2, "tournament": 5, "init_extra": 20, "max_mutations": 3,
        "horizon": 1000000.0, "sample_chars": 0, "sample_chunks": 20, "text_sha256": "x",
        "train_chars": 10, "test_chars": 1, "fit_chars": 10, "cost_params": {}, "penalty_params": {},
        "rival_total": 90.0,
    }  # fmt: skip


def gen_row(g: int, best: float, record: bool) -> dict[str, Any]:
    return {
        "type": "generation", "generation": g, "best_total": best, "gen_best_total": best,
        "mean_total": best + 10.0, "entries": 41, "t_char": 0.3, "memory": 5.0, "record": record,
        "evaluations": 8 * (g + 1),
    }  # fmt: skip


def write_log(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def test_plot_handwritten_log_without_result(tmp_path: Path) -> None:
    log: Path = tmp_path / "log.jsonl"
    write_log(log, [run_row(), gen_row(0, 100.0, True), gen_row(1, 100.0, False), gen_row(2, 95.0, True)])
    png: Path = tmp_path / "out" / "p.png"
    plot_log(log, png)
    assert png.read_bytes()[:8] == PNG


def test_read_log(tmp_path: Path) -> None:
    log: Path = tmp_path / "log.jsonl"
    result: dict[str, Any] = {"type": "result", "best_total": 95.0}
    write_log(log, [run_row(), gen_row(0, 100.0, True), gen_row(1, 95.0, True), result])
    run: dict[str, Any]
    gens: list[dict[str, Any]]
    run, gens = read_log(log)
    assert run["seed"] == 3
    assert [g["generation"] for g in gens] == [0, 1]
    assert all(g["type"] == "generation" for g in gens)


def bad_logs() -> dict[str, str]:
    run: str = json.dumps(run_row())
    gen: str = json.dumps(gen_row(0, 1.0, True))
    alien: dict[str, Any] = run_row() | {"format": "other/format"}
    return {
        "empty": "",
        "only_run": run + "\n",
        "alien_format": json.dumps(alien) + "\n" + gen + "\n",
        "not_json_first": "not json\n" + gen + "\n",
        "not_json_later": run + "\n" + gen + "\n{broken\n",
    }


@pytest.mark.parametrize("name", list(bad_logs()))
def test_bad_logs_rejected(name: str, tmp_path: Path) -> None:
    log: Path = tmp_path / "log.jsonl"
    log.write_text(bad_logs()[name], encoding="utf-8")
    with pytest.raises(ValueError):
        read_log(log)
    code: int
    err: str
    _: str
    code, _, err = run_main(["plot", "--log", str(log)])
    assert code == 1
    assert err.strip() != ""


def test_plot_missing_log(tmp_path: Path) -> None:
    code: int
    _: str
    code, _, _ = run_main(["plot", "--log", str(tmp_path / "нет.jsonl")])
    assert code == 1

"""Checks 25-27: everything without torch (no torch import in this file)."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.helpers import FRAGMENT_PATH, ROOT
from tests.surrogate_helpers import DATA_ARGS, cli_data

MESSAGE: str = "torch is not installed; run `uv sync --extra surrogate`"
BLOCKED: str = (
    "import sys; sys.modules['torch'] = None; from steno_zero.cli import main; "
    "raise SystemExit(main(sys.argv[1:]))"
)
CLEAN: str = (
    "import steno_zero.cli, steno_zero.evolve, steno_zero.surrogate_data, steno_zero.compare, sys; "
    "raise SystemExit(0 if 'torch' not in sys.modules else 3)"
)


def python(code: str, *argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", code, *argv], cwd=ROOT, env=dict(os.environ), capture_output=True, text=True
    )


def test_core_modules_do_not_import_torch() -> None:
    proc: subprocess.CompletedProcess[str] = python(CLEAN)
    assert proc.returncode == 0, proc.stderr


def test_evolve_and_data_work_without_torch(tmp_path: Path) -> None:
    evo: subprocess.CompletedProcess[str] = python(
        BLOCKED, "evolve", "--corpus", str(FRAGMENT_PATH), "--population", "8", "--generations", "2",
        "--workers", "1", "--out", str(tmp_path / "e"),
    )  # fmt: skip
    assert evo.returncode == 0, evo.stderr
    data: subprocess.CompletedProcess[str] = python(
        BLOCKED, "surrogate", "data", "--corpus", str(FRAGMENT_PATH), *DATA_ARGS, "--workers", "1",
        "--out", str(tmp_path / "d.jsonl"),
    )  # fmt: skip
    assert data.returncode == 0, data.stderr
    assert (tmp_path / "d.jsonl").is_file()


@pytest.fixture(scope="module")
def data_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path: Path = tmp_path_factory.mktemp("nt") / "d.jsonl"
    cli_data(path)
    return path


def test_torch_commands_explain_how_to_install(data_path: Path, tmp_path: Path) -> None:
    commands: list[list[str]] = [
        ["surrogate", "train", "--data", str(data_path), "--corpus", str(FRAGMENT_PATH),
         "--epochs", "1", "--hidden", "8", "--out", str(tmp_path / "m.pt")],
        ["surrogate", "compare", "--model", str(tmp_path / "m.pt"), "--corpus", str(FRAGMENT_PATH),
         "--seeds", "2", "--population", "8", "--generations", "2", "--workers", "1",
         "--out", str(tmp_path / "c.json")],
        ["evolve", "--corpus", str(FRAGMENT_PATH), "--population", "8", "--generations", "2",
         "--workers", "1", "--surrogate", str(tmp_path / "m.pt"), "--out", str(tmp_path / "e")],
    ]  # fmt: skip
    argv: list[str]
    for argv in commands:
        proc: subprocess.CompletedProcess[str] = python(BLOCKED, *argv)
        assert proc.returncode == 1, (argv, proc.stderr)
        assert MESSAGE in proc.stderr, (argv, proc.stderr)

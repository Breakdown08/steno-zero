"""Checks 3-6: project files."""

import re
import subprocess
import tomllib
from pathlib import Path
from typing import Any

from tests.helpers import ROOT

CI_COMMANDS: list[str] = [
    "uv sync --locked",
    "uv run ruff check",
    "uv run ruff format --check",
    "uv run ty check",
    "uv run mypy",
    "uv run pytest",
]


def test_ci_has_six_commands_in_order() -> None:
    text: str = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "push" in text
    pos: int = 0
    cmd: str
    for cmd in CI_COMMANDS:
        found: int = text.find(cmd, pos)
        assert found >= 0, f"{cmd!r} missing or out of order"
        pos = found + len(cmd)


def test_no_kadath_in_readme_and_src() -> None:
    readme: Path = ROOT / "README.md"
    assert readme.is_file()
    files: list[Path] = [readme, *sorted((ROOT / "src").rglob("*.py"))]
    p: Path
    for p in files:
        assert "kadath" not in p.read_text(encoding="utf-8").lower(), p


def git_ignored(path: str) -> int:
    return subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT).returncode


def test_gitignore_rules() -> None:
    assert git_ignored("data/corpus/classics.txt") == 0
    assert git_ignored("data/corpus/sources.json") == 1
    assert git_ignored("tests/data/fragment.txt") == 1


def test_pyproject_metadata() -> None:
    data: dict[str, Any] = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project: dict[str, Any] = data["project"]
    assert project["license"] == "Apache-2.0"
    deps: list[str] = project["dependencies"]
    names: set[str] = {re.split(r"[<>=!~ \[]", d, maxsplit=1)[0] for d in deps}
    assert names == {"matplotlib", "numpy", "pandas", "scikit-learn"}
    assert project["requires-python"] == ">=3.14"


def test_runs_dir_is_ignored() -> None:
    assert git_ignored("runs/seed-0/log.jsonl") == 0
    assert git_ignored("data/corpus/classics.txt") == 0
    assert git_ignored("data/corpus/sources.json") == 1


def test_dev_group_and_mypy_override_for_the_new_libraries() -> None:
    data: dict[str, Any] = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dev: list[str] = data["dependency-groups"]["dev"]
    assert any(d.startswith("pandas-stubs") for d in dev)
    overrides: list[dict[str, Any]] = data["tool"]["mypy"]["overrides"]
    sklearn: list[dict[str, Any]] = [o for o in overrides if "sklearn.*" in o["module"]]
    assert len(sklearn) == 1
    assert sklearn[0]["ignore_missing_imports"] is True

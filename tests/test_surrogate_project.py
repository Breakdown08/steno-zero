"""Checks 36-38: pyproject, CI and README for the surrogate."""

import tomllib
from typing import Any

from tests.helpers import ROOT
from tests.page_helpers import section


def pyproject() -> dict[str, Any]:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_torch_dependency_layout() -> None:
    data: dict[str, Any] = pyproject()
    extra: list[str] = data["project"]["optional-dependencies"]["surrogate"]
    assert any(d.startswith("torch") for d in extra)
    assert any(d.startswith("torch") for d in data["dependency-groups"]["dev"])
    assert len(data["project"]["dependencies"]) == 4
    assert not any(d.startswith("torch") for d in data["project"]["dependencies"])


def test_torch_comes_from_the_cpu_index() -> None:
    data: dict[str, Any] = pyproject()
    source: Any = data["tool"]["uv"]["sources"]["torch"]
    sources: list[dict[str, Any]] = source if isinstance(source, list) else [source]
    assert any(s.get("index") == "pytorch-cpu" for s in sources)
    indexes: list[dict[str, Any]] = data["tool"]["uv"]["index"]
    assert {"name": "pytorch-cpu", "url": "https://download.pytorch.org/whl/cpu", "explicit": True} in indexes


def test_ci_enables_the_cache() -> None:
    text: str = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "enable-cache: true" in text


def test_lock_file_knows_torch() -> None:
    assert 'name = "torch"' in (ROOT / "uv.lock").read_text(encoding="utf-8")


def test_readme_surrogate_section() -> None:
    text: str = (ROOT / "README.md").read_text(encoding="utf-8")
    assert (
        text.index("## Evolution result") < text.index("## Surrogate") < text.index("## Fingers and layouts")
    )
    body: str = section(text, "Surrogate")
    needle: str
    for needle in (
        "surrogate data",
        "surrogate train",
        "surrogate compare",
        "--surrogate",
        "--oversample",
        "uv sync --extra surrogate",
        "generation_spearman",
        "download.pytorch.org/whl/cpu",
    ):
        assert needle in body, needle


def test_readme_not_supported() -> None:
    text: str = (ROOT / "README.md").read_text(encoding="utf-8")
    body: str = section(text, "Not supported")
    assert "The neural network." not in body
    assert "Online retraining" in body

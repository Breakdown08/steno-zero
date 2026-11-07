"""Checks 33-37, 39: static page, committed data.js and README."""

import re
import subprocess
from pathlib import Path
from typing import Any

import pytest

from steno_zero.alphabet import normalize
from steno_zero.simulate import segment
from steno_zero.table import Table
from steno_zero.trainer import (
    EXAM_LIMIT,
    HELP_KEY,
    HOME_LIMIT,
    KEY_CODES,
    KEY_LABELS,
    PHRASE_MAX_LEN,
    PHRASE_MIN_LEN,
    chord_label,
    help_order,
    read_data_js,
    table_sha256,
)
from tests.helpers import ROOT, costs

DOCS: Path = ROOT / "docs"
FILES: list[str] = ["index.html", "trainer.js", "data.js"]


def read(name: str) -> str:
    return (DOCS / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("name", FILES)
def test_docs_files_exist_and_tracked(name: str) -> None:
    assert (DOCS / name).is_file()
    code: int = subprocess.run(["git", "check-ignore", "-q", f"docs/{name}"], cwd=ROOT).returncode
    assert code == 1


def test_index_html_structure() -> None:
    html: str = read("index.html")
    data_at: int = html.find('<script src="data.js">')
    js_at: int = html.find('<script src="trainer.js">')
    assert data_at >= 0
    assert js_at > data_at
    assert "<details" in html
    assert "Экзамен" in html


def test_trainer_js_markers() -> None:
    js: str = read("trainer.js")
    needle: str
    for needle in (
        "keydown",
        "keyup",
        "blur",
        "beforeunload",
        "STENO_ZERO_DATA",
        "help_key",
        "exam_size",
        "exam_segments",
        "steno-zero/trainer-log",
    ):
        assert needle in js, needle


def test_trainer_js_has_no_hardcoded_layout() -> None:
    js: str = read("trainer.js")
    code: str
    for code in KEY_CODES:
        assert code not in js, code
    quote: str
    for quote in ('"', "'", "`"):
        assert f"{quote}{HELP_KEY}{quote}" not in js


@pytest.mark.parametrize("name", ["index.html", "trainer.js"])
def test_page_is_self_contained(name: str) -> None:
    text: str = read(name)
    assert "http://" not in text
    assert "https://" not in text
    assert "kadath" not in text.lower()


def test_committed_data_is_consistent() -> None:
    data: dict[str, Any] = read_data_js(DOCS / "data.js")
    assert data["keys"] == [{"code": c, "label": lbl} for c, lbl in zip(KEY_CODES, KEY_LABELS, strict=True)]
    assert data["help_key"] == "Slash"
    assert data["exam_size"] >= 1
    names: list[str] = [t["name"] for t in data["tables"]]
    assert len(names) >= 1
    assert len(set(names)) == len(names)
    assert all(re.fullmatch(r"[a-z0-9-]+", n) for n in names)
    home: list[str] = data["phrases"]
    exam: list[str] = data["exam_phrases"]
    assert home != []
    assert exam != []
    assert len(set(home)) == len(home)
    assert len(set(exam)) == len(exam)
    assert set(home).isdisjoint(exam)
    assert all(normalize(p) == p for p in [*home, *exam])
    assert all(PHRASE_MIN_LEN <= len(p) <= PHRASE_MAX_LEN for p in [*home, *exam])
    assert len(home) <= HOME_LIMIT
    assert len(exam) <= EXAM_LIMIT
    t: dict[str, Any]
    for t in data["tables"]:
        table: Table = Table({p: c for p, c, _ in t["entries"]})
        assert t["sha256"] == table_sha256(table)
        assert t["entries"] == [[p, c, chord_label(c)] for p, c in help_order(table)]
        seg: list[list[list[Any]]]
        phr: list[str]
        for seg, phr in ((t["segments"], home), (t["exam_segments"], exam)):
            assert len(seg) == len(phr)
            k: int
            for k in range(len(phr)):
                assert [c for _, c in seg[k]] == list(segment(phr[k], table, costs()).chords)
                assert "".join(p for p, _ in seg[k]) == phr[k]
                assert all(table.chord(p) == c for p, c in seg[k])


def test_readme_trainer_section() -> None:
    readme: str = (ROOT / "README.md").read_text(encoding="utf-8")
    match: re.Match[str] | None = re.search(r"^## Trainer\s*$(.*?)(?=^## |\Z)", readme, re.S | re.M)
    assert match is not None
    section: str = match.group(1)
    assert "trainer export" in section
    assert "trainer stats" in section
    label: str
    for label in KEY_LABELS:
        assert f"`{label}`" in section, label

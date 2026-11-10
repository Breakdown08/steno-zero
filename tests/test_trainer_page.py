"""Checks 34, 48: committed data.js, tracked files, no foreign words in the new files."""

import re
import subprocess
from pathlib import Path
from typing import Any

import pytest

from steno_zero.alphabet import normalize
from steno_zero.chords import FINGERS
from steno_zero.simulate import segment
from steno_zero.table import Table
from steno_zero.trainer import (
    EXAM_LIMIT,
    HOME_LIMIT,
    PHRASE_MAX_LEN,
    PHRASE_MIN_LEN,
    chord_label,
    help_order,
    read_data_js,
    table_sha256,
)
from tests.helpers import ROOT, costs

DOCS: Path = ROOT / "docs"
TRACKED: list[str] = [
    "docs/index.html",
    "docs/trainer.js",
    "docs/data.js",
    "docs/drill.js",
    "docs/setups.js",
    "data/layouts/qwerty-vm.json",
    "data/keyboards/laptop-vn.json",
]
NEW_FILES: list[str] = [
    "docs/setups.js",
    "docs/drill.js",
    "docs/data.js",
    "data/layouts/qwerty-vm.json",
    "data/keyboards/laptop-vn.json",
    "src/steno_zero/layout.py",
    "src/steno_zero/setups.py",
    "src/steno_zero/keyboard.py",
    "src/steno_zero/drill.py",
    "src/steno_zero/price.py",
]


@pytest.mark.parametrize("name", TRACKED)
def test_files_exist_and_are_not_ignored(name: str) -> None:
    assert (ROOT / name).is_file()
    assert subprocess.run(["git", "check-ignore", "-q", name], cwd=ROOT).returncode == 1


@pytest.mark.parametrize("name", NEW_FILES)
def test_new_files_have_no_foreign_words(name: str) -> None:
    text: str = (ROOT / name).read_text(encoding="utf-8")
    assert "kadath" not in text.lower()
    assert "http://" not in text
    assert "https://" not in text


def test_committed_data_is_consistent() -> None:
    data: dict[str, Any] = read_data_js(DOCS / "data.js")
    assert data["version"] == 2
    assert data["fingers"] == list(FINGERS)
    assert "keys" not in data
    assert data["help_key"] == "Slash"
    assert data["exam_size"] >= 1
    names: list[str] = [t["name"] for t in data["tables"]]
    assert names == ["rival", "evolved"]
    assert [len(t["entries"]) for t in data["tables"]] == [41, 159]
    assert all(re.fullmatch(r"[a-z0-9-]+", n) for n in names)
    home: list[str] = data["phrases"]
    exam: list[str] = data["exam_phrases"]
    assert len(home) == 199
    assert len(exam) == 100
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

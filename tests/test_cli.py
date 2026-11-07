"""Checks 34-38: CLI."""

import json
from pathlib import Path
from typing import Any

import pytest

from steno_zero.cli import main
from steno_zero.corpus import split_corpus
from steno_zero.table import Table
from tests.helpers import BASE, FRAGMENT_PATH, SUMMARY_KEYS, fragment, table_json


def last_json(text: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(text.strip().splitlines()[-1])
    return data


def test_rival_and_evaluate(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out: Path = tmp_path / "r.json"
    assert main(["rival", "--corpus", str(FRAGMENT_PATH), "--out", str(out)]) == 0
    summary: dict[str, Any] = last_json(capsys.readouterr().out)
    assert set(summary) == SUMMARY_KEYS
    assert summary["chars"] == len(fragment())
    assert summary["entries"] == 41
    assert len(Table.from_json(out.read_text(encoding="utf-8"))) == 41

    assert main(["evaluate", "--table", str(out), "--corpus", str(FRAGMENT_PATH)]) == 0
    again: dict[str, Any] = last_json(capsys.readouterr().out)
    assert set(again) == SUMMARY_KEYS
    assert again["total"] == summary["total"]


def test_rival_part_test(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["rival", "--corpus", str(FRAGMENT_PATH), "--part", "test"]) == 0
    summary: dict[str, Any] = last_json(capsys.readouterr().out)
    assert summary["chars"] == len(split_corpus(fragment(), 0.1)[1])


def test_evaluate_bad_table(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    missing: Path = tmp_path / "нет_такого.json"
    assert main(["evaluate", "--table", str(missing), "--corpus", str(FRAGMENT_PATH)]) == 1
    assert capsys.readouterr().err.strip() != ""
    dup: Path = tmp_path / "dup.json"
    dup.write_text(table_json(BASE | {"аа": 1}), encoding="utf-8")
    assert main(["evaluate", "--table", str(dup), "--corpus", str(FRAGMENT_PATH)]) == 1
    assert capsys.readouterr().err.strip() != ""


def test_rival_missing_corpus(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["rival", "--corpus", str(tmp_path / "нет.txt")]) == 1
    assert capsys.readouterr().err.strip() != ""

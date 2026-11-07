"""Checks 26-32: trainer export and stats commands."""

import json
from pathlib import Path
from typing import Any

import pytest

from steno_zero.cli import main
from steno_zero.trainer import read_data_js, split_phrases
from tests.helpers import BASE, FRAGMENT_PATH, base_table, fragment, table_json
from tests.trainer_helpers import EXAMPLE, example_text, log_text

SESSION_KEYS: set[str] = {
    "session",
    "table",
    "started",
    "phrases",
    "chars",
    "time_s",
    "chars_per_min",
    "attempts",
    "misses",
    "miss_rate",
}
SUMMARY_KEYS: set[str] = {
    "sessions",
    "attempts",
    "correct",
    "neighbour_misses",
    "other_misses",
    "slip_prob",
    "median_ms",
}


def lines(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [json.loads(line) for line in text.strip().splitlines()]
    return out


def make_tables(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> tuple[Path, Path]:
    rival: Path = tmp_path / "rival.json"
    assert main(["rival", "--corpus", str(FRAGMENT_PATH), "--out", str(rival)]) == 0
    capsys.readouterr()
    base: Path = tmp_path / "base.json"
    base.write_text(base_table().to_json(), encoding="utf-8")
    return rival, base


def export_args(rival: Path, base: Path, out: Path) -> list[str]:
    return [
        "trainer",
        "export",
        "--table",
        f"rival={rival}",
        "--table",
        f"base={base}",
        "--corpus",
        str(FRAGMENT_PATH),
        "--home-limit",
        "5",
        "--out",
        str(out),
    ]


# 26-28: export


def test_export(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rival: Path
    base: Path
    rival, base = make_tables(tmp_path, capsys)
    out: Path = tmp_path / "d.js"
    assert main(export_args(rival, base, out)) == 0
    summary: dict[str, Any] = lines(capsys.readouterr().out)[-1]
    assert set(summary) == {"out", "phrases", "exam_phrases", "tables"}
    assert summary["phrases"] == 5
    assert summary["tables"] == ["rival", "base"]
    data: dict[str, Any] = read_data_js(out)
    home: list[str]
    exam: list[str]
    home, exam = split_phrases(fragment(), 10, 60, 5, 100)
    assert data["phrases"] == home
    assert data["exam_phrases"] == exam
    assert summary["exam_phrases"] == len(exam)
    assert data["exam_size"] == 5
    assert [t["name"] for t in data["tables"]] == ["rival", "base"]


def test_export_is_deterministic(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rival: Path
    base: Path
    rival, base = make_tables(tmp_path, capsys)
    first: Path = tmp_path / "one.js"
    second: Path = tmp_path / "two.js"
    assert main(export_args(rival, base, first)) == 0
    assert main(export_args(rival, base, second)) == 0
    assert first.read_bytes() == second.read_bytes()


def test_export_exam_size(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rival: Path
    base: Path
    rival, base = make_tables(tmp_path, capsys)
    out: Path = tmp_path / "d.js"
    assert main([*export_args(rival, base, out), "--exam-size", "3"]) == 0
    assert read_data_js(out)["exam_size"] == 3


# 29: export errors


def bad_export_cases(tmp_path: Path, base: Path) -> dict[str, list[str]]:
    dup: Path = tmp_path / "dup.json"
    dup.write_text(table_json(BASE | {"аа": 1}), encoding="utf-8")
    out: list[str] = ["--corpus", str(FRAGMENT_PATH), "--out", str(tmp_path / "x.js")]
    return {
        "no-equals": ["--table", "base", *out],
        "bad-name": ["--table", f"Base={base}", *out],
        "repeated-name": ["--table", f"base={base}", "--table", f"base={base}", *out],
        "missing-file": ["--table", f"base={tmp_path / 'нет.json'}", *out],
        "bad-table": ["--table", f"base={dup}", *out],
        "empty-sets": ["--table", f"base={base}", "--min-len", "70", "--max-len", "80", *out],
        "exam-size-0": ["--table", f"base={base}", "--exam-size", "0", *out],
        "no-corpus": [
            "--table",
            f"base={base}",
            "--corpus",
            str(tmp_path / "нет.txt"),
            "--out",
            str(tmp_path / "x.js"),
        ],
    }


@pytest.mark.parametrize(
    "case",
    [
        "no-equals",
        "bad-name",
        "repeated-name",
        "missing-file",
        "bad-table",
        "empty-sets",
        "exam-size-0",
        "no-corpus",
    ],
)
def test_export_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str], case: str) -> None:
    base: Path = tmp_path / "base.json"
    base.write_text(base_table().to_json(), encoding="utf-8")
    args: list[str] = bad_export_cases(tmp_path, base)[case]
    assert main(["trainer", "export", *args]) == 1
    assert capsys.readouterr().err.strip() != ""


# 30-32: stats


def write_log(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_stats_one_log(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    log: Path = write_log(tmp_path / "l.json", example_text())
    out: Path = tmp_path / "s.json"
    assert main(["trainer", "stats", str(log), "--out", str(out)]) == 0
    rows: list[dict[str, Any]] = lines(capsys.readouterr().out)
    assert len(rows) == 2
    session: dict[str, Any] = rows[0]
    summary: dict[str, Any] = rows[1]
    assert set(session) == SESSION_KEYS
    assert (session["session"], session["table"]) == ("s1", "rival")
    assert session["started"] == "2026-11-08T10:00:00.000Z"
    assert (session["phrases"], session["chars"], session["attempts"], session["misses"]) == (1, 4, 6, 2)
    assert session["time_s"] == pytest.approx(1.0)
    assert session["chars_per_min"] == pytest.approx(240.0)
    assert session["miss_rate"] == pytest.approx(1 / 3)
    assert set(summary) == SUMMARY_KEYS
    assert summary["sessions"] == 1
    assert summary["attempts"] == 6
    assert summary["slip_prob"] == pytest.approx(1 / 56)
    assert summary["median_ms"] == 200.0
    text: str = out.read_text(encoding="utf-8")
    assert "\n  " in text
    full: dict[str, Any] = json.loads(text)
    assert set(full) == SUMMARY_KEYS | {"chords"}
    assert len(full["sessions"]) == 1
    assert set(full["sessions"][0]) == SESSION_KEYS
    assert full["attempts"] == 6
    chords: dict[int, dict[str, Any]] = {c["chord"]: c for c in full["chords"]}
    assert set(chords) == {8, 72}
    assert set(chords[8]) == {"chord", "label", "attempts", "correct", "intervals", "median_ms", "typed"}
    assert chords[8]["typed"] == [[9, 1], [1023, 1]]
    assert chords[8]["median_ms"] is None
    assert chords[72]["label"] == "f j"
    assert chords[72]["median_ms"] == 200.0


def test_stats_two_logs(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    one: Path = write_log(tmp_path / "1.json", example_text())
    two: Path = write_log(tmp_path / "2.json", log_text(EXAMPLE, "s2", "2026-11-09T10:00:00.000Z"))
    assert main(["trainer", "stats", str(two), str(one)]) == 0
    rows: list[dict[str, Any]] = lines(capsys.readouterr().out)
    assert len(rows) == 3
    assert [r["session"] for r in rows[:2]] == ["s1", "s2"]
    assert rows[2]["sessions"] == 2
    assert rows[2]["attempts"] == 12


def test_stats_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    good: Path = write_log(tmp_path / "good.json", example_text())
    again: Path = write_log(tmp_path / "again.json", example_text())
    v2: Path = write_log(tmp_path / "v2.json", example_text().replace('"version": 1', '"version": 2'))
    empty: Path = write_log(
        tmp_path / "empty.json", example_text().split('"attempts"')[0] + '"attempts": []}'
    )
    cases: list[list[str]] = [
        [str(tmp_path / "нет.json")],
        [str(v2)],
        [str(empty)],
        [str(good), str(again)],
    ]
    case: list[str]
    for case in cases:
        assert main(["trainer", "stats", *case]) == 1, case
        assert capsys.readouterr().err.strip() != "", case

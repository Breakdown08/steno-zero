"""Checks 18, 20-23: drill.js data, the trainer drill command and the committed drill.js."""

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from steno_zero.cli import main
from steno_zero.drill import (
    DRILL_PREFIX,
    DRILL_SUFFIX,
    drill_data,
    drill_js,
    drill_plan,
    read_drill_js,
    write_drill_js,
)
from steno_zero.keyboard import calibration_chords
from tests.helpers import ROOT

DATA_KEYS: set[str] = {"format", "version", "seed", "max_keys", "size", "calibration", "blocks"}
SUMMARY_KEYS: set[str] = {"out", "seed", "blocks", "size", "max_keys", "available", "chords", "strata"}


def test_drill_data() -> None:
    data: dict[str, Any] = drill_data(2, 3, 12, 6)
    assert set(data) == DATA_KEYS
    assert data["format"] == "steno-zero/drill-plan"
    assert data["version"] == 2
    assert (data["seed"], data["max_keys"], data["size"]) == (2, 6, 12)
    assert data["calibration"] == list(calibration_chords())
    assert data["blocks"] == [list(b) for b in drill_plan(2, 3, 12, 6)]


def test_drill_js_text_and_round_trip(tmp_path: Path) -> None:
    data: dict[str, Any] = drill_data(0, 3, 10, 6)
    text: str = drill_js(data)
    assert text == DRILL_PREFIX + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + DRILL_SUFFIX
    out: Path = tmp_path / "a" / "b" / "drill.js"
    write_drill_js(data, out)
    assert out.read_bytes() == text.encode("utf-8")
    assert read_drill_js(out) == data


def write(tmp_path: Path, text: str) -> Path:
    path: Path = tmp_path / "drill.js"
    path.write_text(text, encoding="utf-8")
    return path


def test_read_drill_js_rejects_version_1_and_the_rest(tmp_path: Path) -> None:
    data: dict[str, Any] = drill_data(0, 2, 10, 6)
    good: str = drill_js(data)
    assert read_drill_js(write(tmp_path, good)) == data
    bad: list[str] = [
        good.replace(DRILL_PREFIX, "window.OTHER = "),
        good.removesuffix(DRILL_SUFFIX),
        DRILL_PREFIX + "{nope" + DRILL_SUFFIX,
        drill_js({**data, "format": "steno-zero/trainer-data"}),
        drill_js({**data, "version": 1}),
        drill_js({**data, "version": 3}),
    ]
    text: str
    for text in bad:
        with pytest.raises(ValueError):
            read_drill_js(write(tmp_path, text))


def drill_args(out: Path, *extra: str) -> list[str]:
    return ["trainer", "drill", "--out", str(out), *extra]


def test_drill_command_bytes_and_summary(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out: Path = tmp_path / "d" / "drill.js"
    assert main(drill_args(out, "--seed", "0", "--blocks", "4", "--size", "20")) == 0
    first: bytes = out.read_bytes()
    summary: dict[str, Any] = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert set(summary) == SUMMARY_KEYS
    assert summary["out"] == str(out)
    assert (summary["seed"], summary["blocks"], summary["size"], summary["max_keys"]) == (0, 4, 20, 6)
    assert summary["available"] == 847
    assert summary["strata"] == 25
    assert 1 <= summary["chords"] <= 80
    assert first == drill_js(drill_data(0, 4, 20, 6)).encode("utf-8")
    assert main(drill_args(out, "--seed", "0", "--blocks", "4", "--size", "20")) == 0
    capsys.readouterr()
    assert out.read_bytes() == first


def test_drill_command_has_no_keyboard_option(tmp_path: Path) -> None:
    info: pytest.ExceptionInfo[SystemExit]
    with pytest.raises(SystemExit) as info:
        main(["trainer", "drill", "--keyboard", "x", "--out", str(tmp_path / "d.js")])
    assert info.value.code == 2


def test_drill_command_size_too_small(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out: Path = tmp_path / "drill.js"
    assert main(drill_args(out, "--size", "3")) == 1
    assert "error:" in capsys.readouterr().err
    assert not out.exists()


def test_committed_drill_js() -> None:
    path: Path = ROOT / "docs" / "drill.js"
    assert path.is_file()
    assert subprocess.run(["git", "check-ignore", "-q", "docs/drill.js"], cwd=ROOT).returncode == 1
    assert path.read_text(encoding="utf-8") == drill_js(drill_data(0, 100, 100, 6))

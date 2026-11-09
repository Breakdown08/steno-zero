"""Checks 19-21: drill.js data, the trainer drill command and the committed drill.js."""

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
from steno_zero.keyboard import (
    KeyboardProfile,
    available_chords,
    calibration_chords,
    profile_json,
    profile_sha256,
    read_profile,
)
from tests.helpers import ROOT
from tests.keyboard_helpers import P1

DATA_KEYS: set[str] = {
    "format",
    "version",
    "seed",
    "max_keys",
    "size",
    "keyboard",
    "available",
    "calibration",
    "blocks",
}
SUMMARY_KEYS: set[str] = {
    "out",
    "seed",
    "blocks",
    "size",
    "max_keys",
    "keyboard",
    "available",
    "chords",
    "strata",
}


def test_drill_data_without_profile() -> None:
    data: dict[str, Any] = drill_data(2, 3, 12, 6)
    assert set(data) == DATA_KEYS
    assert data["format"] == "steno-zero/drill-plan"
    assert data["version"] == 1
    assert data["seed"] == 2
    assert data["max_keys"] == 6
    assert data["size"] == 12
    assert data["keyboard"] is None
    assert data["available"] == 847
    assert data["calibration"] == list(calibration_chords())
    assert data["blocks"] == [list(b) for b in drill_plan(2, 3, 12, 6)]


def test_drill_data_with_profile() -> None:
    data: dict[str, Any] = drill_data(0, 2, 10, 6, P1)
    assert data["keyboard"] == {"name": "test", "sha256": profile_sha256(P1), "blocked": [152]}
    assert data["available"] == 783
    assert data["calibration"] == list(calibration_chords())
    assert data["blocks"] == [list(b) for b in drill_plan(0, 2, 10, 6, P1)]


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


def test_read_drill_js_rejects(tmp_path: Path) -> None:
    data: dict[str, Any] = drill_data(0, 2, 10, 6)
    good: str = drill_js(data)
    assert read_drill_js(write(tmp_path, good)) == data
    bad: list[str] = [
        good.replace(DRILL_PREFIX, "window.OTHER = "),
        good.removesuffix(DRILL_SUFFIX),
        DRILL_PREFIX + "{nope" + DRILL_SUFFIX,
        drill_js({**data, "format": "steno-zero/trainer-data"}),
        drill_js({**data, "version": 2}),
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
    assert summary["seed"] == 0
    assert summary["blocks"] == 4
    assert summary["size"] == 20
    assert summary["max_keys"] == 6
    assert summary["keyboard"] is None
    assert summary["available"] == 847
    assert summary["strata"] == 25
    assert 1 <= summary["chords"] <= 80
    assert first == drill_js(drill_data(0, 4, 20, 6)).encode("utf-8")
    assert main(drill_args(out, "--seed", "0", "--blocks", "4", "--size", "20")) == 0
    capsys.readouterr()
    assert out.read_bytes() == first


def test_drill_command_with_keyboard(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    profile_path: Path = tmp_path / "test.json"
    profile_path.write_text(profile_json(P1), encoding="utf-8")
    out: Path = tmp_path / "drill.js"
    assert main(drill_args(out, "--keyboard", str(profile_path))) == 0
    summary: dict[str, Any] = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert summary["keyboard"] == "test"
    assert summary["available"] == summary["chords"] == 783
    assert read_drill_js(out)["keyboard"]["sha256"] == profile_sha256(read_profile(profile_json(P1)))


def test_drill_command_size_too_small(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out: Path = tmp_path / "drill.js"
    assert main(drill_args(out, "--size", "3")) == 1
    assert "error:" in capsys.readouterr().err
    assert not out.exists()


def test_committed_drill_js() -> None:
    path: Path = ROOT / "docs" / "drill.js"
    assert path.is_file()
    assert subprocess.run(["git", "check-ignore", "-q", "docs/drill.js"], cwd=ROOT).returncode == 1
    data: dict[str, Any] = read_drill_js(path)
    assert data["seed"] == 0
    assert data["size"] == 100
    assert data["max_keys"] == 6
    assert len(data["blocks"]) == 100
    keyboard: dict[str, Any] | None = data["keyboard"]
    text: str = path.read_text(encoding="utf-8")
    if keyboard is None:
        assert text == drill_js(drill_data(0, 100, 100, 6))
        return
    profile_path: Path = ROOT / "data" / "keyboards" / f"{keyboard['name']}.json"
    assert profile_path.is_file()
    profile: KeyboardProfile = read_profile(profile_path.read_text(encoding="utf-8"))
    assert profile_sha256(profile) == keyboard["sha256"]
    assert text == drill_js(drill_data(0, 100, 100, 6, profile))
    assert data["available"] == len(available_chords(6, profile))

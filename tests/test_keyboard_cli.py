"""Check 43: the keyboard profile command."""

import json
from pathlib import Path
from typing import Any

import pytest

from steno_zero.cli import main
from steno_zero.keyboard import KeyboardProfile, profile_json, read_profile
from tests.keyboard_helpers import CHECK5, calibration_text, count_available

SUMMARY_KEYS: set[str] = {"out", "name", "keys", "blocked", "unclear", "available"}


def write_log(tmp_path: Path, overrides: dict[int, list[int]] | None = None) -> Path:
    path: Path = tmp_path / "calibration.json"
    path.write_text(calibration_text(overrides), encoding="utf-8")
    return path


def test_profile_command_summary_and_bytes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    log: Path = write_log(tmp_path, CHECK5)
    out: Path = tmp_path / "tmp" / "k.json"
    assert main(["keyboard", "profile", str(log), "--name", "test", "--out", str(out)]) == 0
    first: bytes = out.read_bytes()
    summary: dict[str, Any] = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert set(summary) == SUMMARY_KEYS
    assert summary["out"] == str(out)
    assert summary["name"] == "test"
    assert summary["blocked"] == ["KeyA+KeyD+KeyS", "KeyF+KeyK+KeyV"]
    assert summary["unclear"] == ["KeyA+KeyD+KeyS"]
    assert summary["available"] == count_available(6, (7, 152))
    profile: KeyboardProfile = read_profile(out.read_text(encoding="utf-8"))
    assert out.read_text(encoding="utf-8") == profile_json(profile)
    assert main(["keyboard", "profile", str(log), "--name", "test", "--out", str(out)]) == 0
    capsys.readouterr()
    assert out.read_bytes() == first


def test_profile_command_max_keys(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    log: Path = write_log(tmp_path, CHECK5)
    out: Path = tmp_path / "k.json"
    assert (
        main(["keyboard", "profile", str(log), "--name", "test", "--out", str(out), "--max-keys", "4"]) == 0
    )
    summary: dict[str, Any] = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert summary["available"] == count_available(4, (7, 152))


def test_profile_command_rejects_target_outside_the_list(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    obj: dict[str, Any] = json.loads(calibration_text())
    obj["attempts"][0]["target"] = 15
    log: Path = tmp_path / "bad.json"
    log.write_text(json.dumps(obj), encoding="utf-8")
    out: Path = tmp_path / "k.json"
    assert main(["keyboard", "profile", str(log), "--name", "test", "--out", str(out)]) == 1
    assert "error:" in capsys.readouterr().err
    assert not out.exists()


def test_profile_command_version_1_log(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    obj: dict[str, Any] = json.loads(calibration_text())
    obj["version"] = 1
    del obj["layout"]
    log: Path = tmp_path / "v1.json"
    log.write_text(json.dumps(obj), encoding="utf-8")
    assert main(["keyboard", "profile", str(log), "--name", "test", "--out", str(tmp_path / "k.json")]) == 1
    assert "version 1 is no longer read" in capsys.readouterr().err


def test_profile_command_incomplete_calibration(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    obj: dict[str, Any] = json.loads(calibration_text())
    obj["attempts"] = obj["attempts"][1:]
    log: Path = tmp_path / "short.json"
    log.write_text(json.dumps(obj), encoding="utf-8")
    assert main(["keyboard", "profile", str(log), "--name", "test", "--out", str(tmp_path / "k.json")]) == 1
    assert "error:" in capsys.readouterr().err


def test_profile_command_missing_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["keyboard", "profile", str(tmp_path / "none.json"), "--name", "test"]) == 1
    assert "error:" in capsys.readouterr().err

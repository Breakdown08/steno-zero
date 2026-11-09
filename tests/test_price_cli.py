"""Checks 36-38: the price fit command."""

import json
from pathlib import Path
from typing import Any

import pytest

from steno_zero.cli import main
from steno_zero.keyboard import profile_json
from tests.keyboard_helpers import P1, P2
from tests.price_helpers import (
    keyboard_of,
    main_logs,
    main_plan,
    p1_logs,
    synth_logs,
    write_logs,
)
from tests.trainer_helpers import example_text

SUMMARY_KEYS: set[str] = {
    "out",
    "rows",
    "time_rows",
    "chords_seen",
    "chosen",
    "mae_ms",
    "miss_model",
    "keyboard",
    "suspects",
}


@pytest.fixture(scope="module")
def synth_files(tmp_path_factory: pytest.TempPathFactory) -> list[Path]:
    return write_logs(main_logs(), tmp_path_factory.mktemp("synth"))


@pytest.fixture(scope="module")
def p1_files(tmp_path_factory: pytest.TempPathFactory) -> list[Path]:
    return write_logs(p1_logs(), tmp_path_factory.mktemp("p1"))


def run_fit(files: list[Path], out: Path, *extra: str) -> int:
    return main(["price", "fit", *[str(f) for f in files], "--out", str(out), *extra])


def last_line(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    out: dict[str, Any] = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    return out


def test_fit_writes_prices_and_report(
    synth_files: list[Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out: Path = tmp_path / "price"
    assert run_fit(synth_files, out) == 0
    summary: dict[str, Any] = last_line(capsys)
    prices_text: str = (out / "prices.json").read_text(encoding="utf-8")
    report_text: str = (out / "report.json").read_text(encoding="utf-8")
    prices: dict[str, Any] = json.loads(prices_text)
    report: dict[str, Any] = json.loads(report_text)
    assert prices["format"] == "steno-zero/chord-prices"
    assert report["format"] == "steno-zero/chord-price-report"
    assert prices_text == json.dumps(prices, ensure_ascii=False, indent=1) + "\n"
    assert report_text == json.dumps(report, ensure_ascii=False, indent=1) + "\n"
    assert set(summary) == SUMMARY_KEYS
    assert summary["out"] == str(out)
    assert summary["rows"] == report["rows"] == 2850
    assert summary["time_rows"] == report["time_rows"]
    assert summary["chords_seen"] == report["chords_seen"]
    assert summary["chosen"] == report["chosen"]
    assert set(summary["mae_ms"]) == {"baseline", "ridge", "boosting"}
    assert summary["miss_model"] == prices["miss_model"]
    assert summary["keyboard"] is None
    assert summary["suspects"] == len(report["suspect_chords"])


def test_fit_options(synth_files: list[Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out: Path = tmp_path / "opts"
    args: list[str] = [
        "--target",
        "motor",
        "--model",
        "ridge",
        "--folds",
        "3",
        "--seed",
        "4",
        "--skip-first",
        "0",
    ]
    assert run_fit(synth_files, out, *args, "--max-ms", "4000", "--max-keys", "6") == 0
    capsys.readouterr()
    report: dict[str, Any] = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert report["target"] == "motor"
    assert report["folds"] == 3
    assert report["seed"] == 4
    assert report["max_ms"] == 4000.0
    assert report["rows"] == 3000
    assert report["chosen"] == "ridge"


def test_fit_is_reproducible(
    synth_files: list[Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_fit(synth_files, tmp_path / "one") == 0
    assert run_fit(synth_files, tmp_path / "two") == 0
    capsys.readouterr()
    name: str
    for name in ("prices.json", "report.json"):
        assert (tmp_path / "one" / name).read_bytes() == (tmp_path / "two" / name).read_bytes()


def expect_error(code: int, capsys: pytest.CaptureFixture[str], *needles: str) -> None:
    assert code == 1
    err: str = capsys.readouterr().err
    assert "error:" in err
    needle: str
    for needle in needles:
        assert needle in err


def test_fit_rejects_an_exam_log(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exam: Path = tmp_path / "exam.json"
    exam.write_text(example_text(), encoding="utf-8")
    expect_error(run_fit([exam], tmp_path / "o"), capsys, "exam.json")


def test_fit_rejects_a_missing_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    expect_error(run_fit([tmp_path / "nothing.json"], tmp_path / "o"), capsys, "nothing.json")


def test_fit_rejects_the_same_session_twice(
    synth_files: list[Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    expect_error(run_fit([*synth_files, synth_files[0]], tmp_path / "o"), capsys)


def test_fit_rejects_mixed_keyboards(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with_profile: list[Path] = write_logs(
        synth_logs(main_plan()[:3], keyboard_of(P1), prefix="p"), tmp_path / "a"
    )
    without_profile: list[Path] = write_logs(synth_logs(main_plan()[:3], None, prefix="n"), tmp_path / "b")
    expect_error(run_fit([*with_profile, *without_profile], tmp_path / "o"), capsys, "different keyboards")


def test_fit_rejects_a_profile_log_without_the_keyboard_option(
    p1_files: list[Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    expect_error(run_fit(p1_files, tmp_path / "o"), capsys)


def test_fit_rejects_a_foreign_profile(
    p1_files: list[Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    foreign: Path = tmp_path / "foreign.json"
    foreign.write_text(profile_json(P2), encoding="utf-8")
    expect_error(run_fit(p1_files, tmp_path / "o", "--keyboard", str(foreign)), capsys)


def test_fit_with_the_right_profile(
    p1_files: list[Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    profile: Path = tmp_path / "test.json"
    profile.write_text(profile_json(P1), encoding="utf-8")
    out: Path = tmp_path / "o"
    assert run_fit(p1_files, out, "--keyboard", str(profile)) == 0
    assert last_line(capsys)["keyboard"] == "test"
    prices: dict[str, Any] = json.loads((out / "prices.json").read_text(encoding="utf-8"))
    assert prices["available"] == 783
    assert prices["unavailable"] == 64
    unavailable: list[int] = [r["chord"] for r in prices["prices"] if not r["available"]]
    assert 152 in unavailable
    assert len(unavailable) == 64

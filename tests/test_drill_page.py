"""Checks 2, 39-41: the page with the new modes, the new files and the README."""

import re
import subprocess
from pathlib import Path

from steno_zero.trainer import KEY_CODES
from tests.helpers import ROOT

DOCS: Path = ROOT / "docs"


def read(name: str) -> str:
    return (DOCS / name).read_text(encoding="utf-8")


def section(readme: str, title: str) -> str:
    match: re.Match[str] | None = re.search(
        rf"^## {re.escape(title)}\s*$(.*?)(?=^## |\Z)", readme, re.S | re.M
    )
    assert match is not None, title
    return match.group(1)


def test_drill_js_is_tracked() -> None:
    assert (DOCS / "drill.js").is_file()
    assert subprocess.run(["git", "check-ignore", "-q", "docs/drill.js"], cwd=ROOT).returncode == 1


def test_index_html_scripts_and_new_elements() -> None:
    html: str = read("index.html")
    data_at: int = html.find('<script src="data.js">')
    drill_at: int = html.find('<script src="drill.js">')
    js_at: int = html.find('<script src="trainer.js">')
    assert data_at >= 0
    assert drill_at > data_at
    assert js_at > drill_at
    needle: str
    for needle in (
        'id="drill"',
        'id="calibrate"',
        'id="target"',
        "Случайные аккорды",
        "Калибровка клавиатуры",
    ):
        assert needle in html, needle


def test_trainer_js_markers() -> None:
    js: str = read("trainer.js")
    needle: str
    for needle in (
        "STENO_ZERO_DRILL",
        "steno-zero/drill-log",
        "steno-zero/keyboard-calibration",
        "shown_ms",
        "block",
        "presentations",
        "calibration",
        "keyboard",
    ):
        assert needle in js, needle
    code: str
    for code in KEY_CODES:
        assert code not in js, code


def test_drill_js_is_self_contained() -> None:
    text: str = read("drill.js")
    assert "http://" not in text
    assert "https://" not in text
    assert "kadath" not in text.lower()


def test_no_kadath_in_new_python_modules_and_profiles() -> None:
    files: list[Path] = [ROOT / "src" / "steno_zero" / f"{m}.py" for m in ("keyboard", "drill", "price")]
    files.append(DOCS / "drill.js")
    files += sorted((ROOT / "data" / "keyboards").glob("*")) if (ROOT / "data" / "keyboards").is_dir() else []
    path: Path
    for path in files:
        assert path.is_file(), path
        assert "kadath" not in path.read_text(encoding="utf-8").lower(), path


def test_readme_sections() -> None:
    readme: str = (ROOT / "README.md").read_text(encoding="utf-8")
    trainer: str = section(readme, "Trainer")
    needle: str
    for needle in ("trainer drill", "keyboard profile", "steno-zero/drill-log"):
        assert needle in trainer, needle
    prices: str = section(readme, "Chord prices")
    assert "price fit" in prices
    assert "GroupKFold" in prices
    unsupported: str = section(readme, "Not supported")
    assert "random-chord mode" not in unsupported
    assert "keyboard profile" in unsupported.lower()

"""Checks 49-51: the README sections."""

from steno_zero.chords import FINGERS
from tests.helpers import ROOT
from tests.page_helpers import section


def readme() -> str:
    return (ROOT / "README.md").read_text(encoding="utf-8")


def test_fingers_and_layouts_section() -> None:
    needle: str
    text: str = readme()
    body: str = section(text, "Fingers and layouts")
    assert text.index("## Fingers and layouts") < text.index("## Trainer")
    name: str
    for name in FINGERS:
        assert f"`{name}`" in body, name
    for needle in ("qwerty-vm", "KeyM", "trainer setups", "data/layouts"):
        assert needle in body, needle


def test_trainer_section() -> None:
    needle: str
    body: str = section(readme(), "Trainer")
    for needle in ("trainer export", "trainer stats", "trainer drill", "keyboard profile"):
        assert needle in body, needle
    for needle in ("can be fixed before release", "version 2", "laptop-vn"):
        assert needle in body, needle
    for needle in ("steno-zero/drill-log", "trainer-log", "version 1 files", "are not read"):
        assert needle in body, needle
    assert "`n`" not in body
    assert "right index, down" not in body
    assert "left index, down" not in body


def test_chord_prices_section() -> None:
    needle: str
    body: str = section(readme(), "Chord prices")
    for needle in ("--layout", "thumb_index", "GroupKFold", "price fit"):
        assert needle in body, needle


def test_not_supported_section() -> None:
    body: str = section(readme(), "Not supported").lower()
    assert "keyboard profile" in body
    assert "layout feature" in body
    assert "random-chord mode" not in body

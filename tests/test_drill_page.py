"""The page modes of random chords and calibration: markers of trainer.js that the log formats need."""

from tests.page_helpers import read


def test_index_html_has_the_modes() -> None:
    html: str = read("index.html")
    needle: str
    for needle in ('id="drill"', 'id="calibrate"', "Случайные аккорды", "Калибровка клавиатуры"):
        assert needle in html, needle


def test_trainer_js_markers_of_the_logs() -> None:
    js: str = read("trainer.js")
    needle: str
    for needle in (
        "STENO_ZERO_DRILL",
        "STENO_ZERO_SETUPS",
        "steno-zero/drill-log",
        "steno-zero/keyboard-calibration",
        "shown_ms",
        "block",
        "presentations",
        "calibration",
        "keyboard",
        "layout",
    ):
        assert needle in js, needle

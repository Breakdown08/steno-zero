"""Checks 44-47: the static part of the page: scripts, hands, CSS, trainer.js markers."""

import json
import re
from pathlib import Path

import pytest

from steno_zero.chords import FINGERS
from tests.helpers import ROOT
from tests.layout_helpers import FINGER_NAMES, VM_CODES
from tests.page_helpers import Node, css_rules, index_dom, read, style_text

RUSSIAN: tuple[str, ...] = (
    "л. мизинец",
    "л. безымянный",
    "л. средний",
    "л. указательный",
    "л. большой",
    "пр. большой",
    "пр. указательный",
    "пр. средний",
    "пр. безымянный",
    "пр. мизинец",
)


def by_id(root: Node, ident: str) -> list[Node]:
    return [n for n in root.walk() if n.attrs.get("id") == ident]


def layout_codes() -> set[str]:
    codes: set[str] = set(VM_CODES)
    path: Path
    for path in sorted((ROOT / "data" / "layouts").glob("*.json")):
        obj: dict[str, list[dict[str, str]]] = json.loads(path.read_text(encoding="utf-8"))
        codes |= {k["code"] for k in obj["keys"]}
    return codes


def test_scripts_in_order() -> None:
    html: str = read("index.html")
    positions: list[int] = [
        html.find(f'<script src="{name}">') for name in ("data.js", "drill.js", "setups.js", "trainer.js")
    ]
    assert all(p >= 0 for p in positions), positions
    assert positions == sorted(positions)


def test_ids_present_and_old_scheme_gone() -> None:
    root: Node = index_dom()
    ident: str
    for ident in (
        "setup",
        "hands",
        "target",
        "target-label",
        "target-note",
        "held",
        "drill",
        "calibrate",
        "layout",
    ):
        assert len(by_id(root, ident)) == 1, ident
    for ident in ("left", "right", "target-left", "target-right", "keys"):
        assert by_id(root, ident) == [], ident
    assert by_id(root, "setup")[0].tag == "select"
    assert by_id(root, "hands")[0].tag == "svg"
    html: str = read("index.html")
    assert "<img" not in html
    assert "http://" not in html
    assert "https://" not in html
    assert "kadath" not in html.lower()
    assert "<details" in html
    assert "Экзамен" in html


def test_no_element_of_the_old_key_row_is_left() -> None:
    """Spec 44 forbids class="key"; the hands need <text class="key">, so only that one is allowed."""
    root: Node = index_dom()
    old: list[Node] = [
        n for n in root.walk() if "key" in n.classes and not (n.tag == "text" and n.inside("hands"))
    ]
    assert old == []


def fingers(root: Node) -> list[Node]:
    return [n for n in by_id(root, "hands")[0].walk() if n.tag == "g" and "finger" in n.classes]


def test_ten_fingers_in_order() -> None:
    root: Node = index_dom()
    gs: list[Node] = fingers(root)
    assert len(gs) == 10
    assert [g.attrs.get("data-finger") for g in gs] == [str(i) for i in range(10)]
    assert len(by_id(root, "hands")[0].walk()) > 10


def tip(g: Node) -> Node:
    tips: list[Node] = [n for n in g.walk() if n.tag == "ellipse" and "tip" in n.classes]
    assert len(tips) == 1
    return tips[0]


def test_each_finger_has_its_parts() -> None:
    gs: list[Node] = fingers(index_dom())
    i: int
    g: Node
    for i, g in enumerate(gs):
        t: Node = tip(g)
        assert t.attrs["data-finger"] == str(i)
        attr: str
        for attr in ("cx", "cy", "rx", "ry"):
            float(t.attrs[attr])
        crosses: list[Node] = [n for n in g.walk() if n.tag == "path" and "cross" in n.classes]
        assert len(crosses) == 1
        assert crosses[0].attrs.get("d", "") != ""
        names: list[Node] = [n for n in g.walk() if n.tag == "text" and "name" in n.classes]
        assert len(names) == 1
        assert names[0].text.strip() == FINGERS[i] == FINGER_NAMES[i]
        keys: list[Node] = [n for n in g.walk() if n.tag == "text" and "key" in n.classes]
        assert len(keys) == 1
        assert keys[0].text.strip() == ""


def test_geometry_of_the_hands() -> None:
    gs: list[Node] = fingers(index_dom())
    cx: list[float] = [float(tip(g).attrs["cx"]) for g in gs]
    cy: list[float] = [float(tip(g).attrs["cy"]) for g in gs]
    assert cx == sorted(set(cx))
    assert cy[4] > max(cy[0:4])
    assert cy[5] > max(cy[6:10])


def test_palms_are_drawn() -> None:
    palms: list[Node] = [
        n for n in by_id(index_dom(), "hands")[0].walk() if n.tag == "path" and "palm" in n.classes
    ]
    assert len(palms) >= 1


def test_css_states() -> None:
    css: str = style_text(index_dom())
    state: str
    for state in ("wait", "ok", "extra", "held"):
        assert f".finger.{state}" in css, state
    rules: list[tuple[str, str]] = css_rules(css)
    dashed: list[str] = [
        body for sel, body in rules if ".finger.wait" in sel and re.search(r"stroke-dasharray:\s*[^;n]", body)
    ]
    assert dashed != []
    hidden: list[str] = [
        sel
        for sel, body in rules
        if ".cross" in sel
        and ".finger" not in sel
        and re.search(r"display:\s*none|visibility:\s*hidden", body)
    ]
    assert hidden != []
    shown: list[str] = [
        body
        for sel, body in rules
        if ".finger.extra" in sel
        and ".cross" in sel
        and re.search(r"display:\s*(inline|block|initial|unset)|visibility:\s*visible", body)
    ]
    assert shown != []


def test_trainer_js_markers() -> None:
    js: str = read("trainer.js")
    needle: str
    for needle in (
        "STENO_ZERO_SETUPS",
        "STENO_ZERO_DRILL",
        "layout",
        "blocked",
        "plan",
        "wait",
        "extra",
        "held",
        "setup",
        "steno-zero/drill-log",
        "steno-zero/keyboard-calibration",
        "steno-zero/trainer-log",
    ):
        assert needle in js, needle


def test_no_key_code_of_a_layout_in_the_page() -> None:
    texts: dict[str, str] = {name: read(name) for name in ("trainer.js", "index.html")}
    name: str
    text: str
    code: str
    for name, text in texts.items():
        for code in sorted(layout_codes()):
            assert not re.search(rf"\b{code}\b", text), (name, code)


def test_versions_in_trainer_js() -> None:
    js: str = read("trainer.js")
    assert re.search(r"version:\s*1\b", js) is None
    assert re.search(r"version:\s*2\b", js) is not None


def test_help_lists_fingers_in_russian_and_the_plan_warning_stays() -> None:
    text: str = read("index.html") + read("trainer.js")
    assert all(name in text for name in RUSSIAN)
    assert "без профиля" in text


@pytest.mark.parametrize("name", ["index.html", "trainer.js", "drill.js", "setups.js", "data.js"])
def test_page_files_are_self_contained(name: str) -> None:
    text: str = read(name)
    assert "http://" not in text
    assert "https://" not in text
    assert "kadath" not in text.lower()

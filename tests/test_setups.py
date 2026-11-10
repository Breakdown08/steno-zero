"""Checks 27-32: setups (layout + profile), setups.js and the trainer setups command."""

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from steno_zero.cli import main
from steno_zero.drill import drill_data, drill_js, drill_plan, read_drill_js
from steno_zero.keyboard import KeyboardProfile, profile_json, profile_sha256, read_profile
from steno_zero.layout import Layout, read_layouts
from steno_zero.setups import (
    SETUPS_PREFIX,
    SETUPS_SUFFIX,
    read_setups_js,
    setup_name,
    setups_data,
    setups_js,
    write_setups_js,
)
from tests.drill_helpers import LAPTOP_OLD_BLOCKED
from tests.helpers import ROOT
from tests.keyboard_helpers import LAPTOP_VN, P1
from tests.layout_helpers import VM, ZZ, layout_obj_of, layout_text

TEST_PROFILE: KeyboardProfile = P1  # named "test", covers qwerty-vm, blocks KeyF KeyK KeyV


def drill() -> dict[str, Any]:
    return drill_data(2, 3, 12, 6)


def test_setup_names() -> None:
    assert setup_name(VM, None) == "qwerty-vm"
    assert setup_name(VM, TEST_PROFILE) == "qwerty-vm@test"


def test_one_layout_without_profiles() -> None:
    data: dict[str, Any] = setups_data([VM], [], drill())
    assert data["format"] == "steno-zero/setups"
    assert data["version"] == 1
    assert data["drill"] == {"seed": 2, "blocks": 3, "size": 12, "max_keys": 6}
    assert data["setups"] == [
        {"name": "qwerty-vm", "layout": layout_obj_of(VM), "keyboard": None, "blocked": [], "plan": None}
    ]


def test_order_blocked_keyboard_and_plan() -> None:
    data: dict[str, Any] = setups_data([VM, ZZ], [TEST_PROFILE, LAPTOP_VN], drill())
    setups: list[dict[str, Any]] = data["setups"]
    assert [s["name"] for s in setups] == ["qwerty-vm@test", "qwerty-vm", "zz@laptop-vn", "zz"]
    first: dict[str, Any] = setups[0]
    assert first["layout"] == layout_obj_of(VM)
    assert first["blocked"] == [152]
    assert first["keyboard"] == {"name": "test", "sha256": profile_sha256(TEST_PROFILE)}
    assert first["plan"] == [list(b) for b in drill_plan(2, 3, 12, 6, (152,))]
    assert len(first["plan"]) == 3
    assert all(len(block) == 12 for block in first["plan"])
    assert all(c & 152 != 152 for block in first["plan"] for c in block)
    third: dict[str, Any] = setups[2]
    assert third["blocked"] == sorted(LAPTOP_OLD_BLOCKED)
    assert third["keyboard"] == {"name": "laptop-vn", "sha256": profile_sha256(LAPTOP_VN)}
    assert third["plan"] == [list(b) for b in drill_plan(2, 3, 12, 6, LAPTOP_OLD_BLOCKED)]
    assert setups[1]["plan"] is None
    assert setups[3]["plan"] is None
    assert setups[1]["keyboard"] is None
    assert setups[1]["blocked"] == []


def test_order_does_not_depend_on_the_order_of_the_input() -> None:
    forward: dict[str, Any] = setups_data([VM, ZZ], [TEST_PROFILE, LAPTOP_VN], drill())
    backward: dict[str, Any] = setups_data([ZZ, VM], [LAPTOP_VN, TEST_PROFILE], drill())
    assert [s["name"] for s in backward["setups"]] == [s["name"] for s in forward["setups"]]


def test_a_profile_that_does_not_cover_the_layout_is_skipped() -> None:
    data: dict[str, Any] = setups_data([VM], [LAPTOP_VN], drill())
    assert [s["name"] for s in data["setups"]] == ["qwerty-vm"]


def test_setups_data_errors() -> None:
    with pytest.raises(ValueError):
        setups_data([], [], drill())
    with pytest.raises(ValueError):
        setups_data([VM, VM], [], drill())
    with pytest.raises(ValueError):
        setups_data([VM], [TEST_PROFILE, TEST_PROFILE], drill())


def test_setups_js_round_trip(tmp_path: Path) -> None:
    data: dict[str, Any] = setups_data([VM, ZZ], [TEST_PROFILE], drill())
    text: str = setups_js(data)
    assert text == SETUPS_PREFIX + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + SETUPS_SUFFIX
    out: Path = tmp_path / "a" / "setups.js"
    write_setups_js(data, out)
    assert out.read_bytes() == text.encode("utf-8")
    assert read_setups_js(out) == data


def test_read_setups_js_rejects(tmp_path: Path) -> None:
    data: dict[str, Any] = setups_data([VM], [], drill())
    good: str = setups_js(data)
    path: Path = tmp_path / "setups.js"
    path.write_text(good, encoding="utf-8")
    assert read_setups_js(path) == data
    bad: list[str] = [
        good.replace(SETUPS_PREFIX, "window.OTHER = "),
        good.removesuffix(SETUPS_SUFFIX),
        SETUPS_PREFIX + "{nope" + SETUPS_SUFFIX,
        setups_js({**data, "format": "steno-zero/drill-plan"}),
        setups_js({**data, "version": 2}),
    ]
    text: str
    for text in bad:
        path.write_text(text, encoding="utf-8")
        with pytest.raises(ValueError):
            read_setups_js(path)


def make_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    layouts: Path = tmp_path / "layouts"
    keyboards: Path = tmp_path / "keyboards"
    layouts.mkdir()
    keyboards.mkdir()
    (layouts / "qwerty-vm.json").write_text(layout_text(VM), encoding="utf-8")
    (layouts / "zz.json").write_text(layout_text(ZZ), encoding="utf-8")
    (keyboards / "test.json").write_text(profile_json(TEST_PROFILE), encoding="utf-8")
    (keyboards / "laptop-vn.json").write_text(profile_json(LAPTOP_VN), encoding="utf-8")
    plan: Path = tmp_path / "drill.js"
    plan.write_text(drill_js(drill()), encoding="utf-8")
    return layouts, keyboards, plan


def expected_text(layouts: Path, keyboards: Path, plan: Path) -> str:
    profiles: list[KeyboardProfile] = [
        read_profile(p.read_text(encoding="utf-8")) for p in sorted(keyboards.glob("*.json"))
    ]
    all_layouts: tuple[Layout, ...] = read_layouts(layouts)
    return setups_js(setups_data(all_layouts, profiles, read_drill_js(plan)))


def test_setups_command(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    layouts: Path
    keyboards: Path
    plan: Path
    layouts, keyboards, plan = make_inputs(tmp_path)
    out: Path = tmp_path / "out" / "setups.js"
    args: list[str] = [
        "trainer",
        "setups",
        "--layouts",
        str(layouts),
        "--keyboards",
        str(keyboards),
        "--drill",
        str(plan),
        "--out",
        str(out),
    ]
    assert main(args) == 0
    summary: dict[str, Any] = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert set(summary) == {"out", "setups"}
    assert summary["out"] == str(out)
    assert summary["setups"] == ["qwerty-vm@test", "qwerty-vm", "zz@laptop-vn", "zz"]
    assert out.read_text(encoding="utf-8") == expected_text(layouts, keyboards, plan)


def test_setups_command_without_a_keyboards_folder(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    layouts: Path
    unused: Path
    plan: Path
    layouts, unused, plan = make_inputs(tmp_path)
    out: Path = tmp_path / "setups.js"
    code: int = main(
        [
            "trainer",
            "setups",
            "--layouts",
            str(layouts),
            "--keyboards",
            str(tmp_path / "nothing"),
            "--drill",
            str(plan),
            "--out",
            str(out),
        ]
    )
    assert code == 0
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["setups"] == ["qwerty-vm", "zz"]


def test_setups_command_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    layouts: Path
    keyboards: Path
    plan: Path
    layouts, keyboards, plan = make_inputs(tmp_path)
    out: Path = tmp_path / "setups.js"
    base: list[str] = ["trainer", "setups", "--keyboards", str(keyboards), "--out", str(out)]

    missing: Path = tmp_path / "nothing.js"
    assert main([*base, "--layouts", str(layouts), "--drill", str(missing)]) == 1
    assert "error:" in capsys.readouterr().err
    assert not out.exists()

    assert main([*base, "--layouts", str(tmp_path / "no-layouts"), "--drill", str(plan)]) == 1
    assert "error:" in capsys.readouterr().err
    assert not out.exists()

    (layouts / "broken.json").write_text("{", encoding="utf-8")
    assert main([*base, "--layouts", str(layouts), "--drill", str(plan)]) == 1
    err: str = capsys.readouterr().err
    assert "error:" in err
    assert "broken.json" in err
    assert not out.exists()

    (layouts / "broken.json").unlink()
    plan.write_text("not a drill.js", encoding="utf-8")
    assert main([*base, "--layouts", str(layouts), "--drill", str(plan)]) == 1
    assert "error:" in capsys.readouterr().err
    assert not out.exists()


def test_committed_setups_js(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path: Path = ROOT / "docs" / "setups.js"
    assert path.is_file()
    out: Path = tmp_path / "setups.js"
    code: int = main(
        [
            "trainer",
            "setups",
            "--layouts",
            str(ROOT / "data" / "layouts"),
            "--keyboards",
            str(ROOT / "data" / "keyboards"),
            "--drill",
            str(ROOT / "docs" / "drill.js"),
            "--out",
            str(out),
        ]
    )
    assert code == 0
    capsys.readouterr()
    assert path.read_bytes() == out.read_bytes()
    data: dict[str, Any] = read_setups_js(path)
    names: list[str] = [s["name"] for s in data["setups"]]
    assert names[0] == "qwerty-vm"
    assert not any("laptop-vn" in n for n in names)
    assert subprocess.run(["git", "check-ignore", "-q", "docs/setups.js"], cwd=ROOT).returncode == 1

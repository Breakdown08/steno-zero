"""Checks 15-17: the migrated profile laptop-vn."""

from pathlib import Path

import pytest

from steno_zero.keyboard import KeyboardError, KeyboardProfile, finger_blocked, profile_json, read_profile
from tests.drill_helpers import LAPTOP_OLD_BLOCKED
from tests.helpers import ROOT
from tests.layout_helpers import OLD_CODES, VM

FOLDER: Path = ROOT / "data" / "keyboards"
EXPECTED: tuple[tuple[str, ...], ...] = (
    ("KeyA", "KeyD", "KeyJ"),
    ("KeyA", "KeyD", "KeyK"),
    ("KeyD", "KeyF", "KeyV"),
    ("KeyD", "KeyJ", "KeyV"),
    ("KeyD", "KeyN", "KeyV"),
    ("KeyF", "KeyK", "KeyV"),
    ("KeyF", "KeyL", "KeyV"),
    ("KeyF", "KeyV", "Semicolon"),
)


def test_old_profile_is_gone() -> None:
    assert not (FOLDER / "laptop.json").exists()


def test_laptop_vn_is_read() -> None:
    path: Path = FOLDER / "laptop-vn.json"
    text: str = path.read_text(encoding="utf-8")
    profile: KeyboardProfile = read_profile(text)
    assert profile.name == "laptop-vn"
    assert profile.session == "calibration-2026-11-09T09-57-23.069Z"
    assert profile.created == "2026-11-09T09:57:23.069Z"
    assert profile.keys == (
        "KeyA",
        "KeyD",
        "KeyF",
        "KeyJ",
        "KeyK",
        "KeyL",
        "KeyN",
        "KeyS",
        "KeyV",
        "Semicolon",
    )
    assert len(profile.blocked) == 8
    assert sorted(b.keys for b in profile.blocked) == sorted(EXPECTED)
    assert all(b.unclear for b in profile.blocked)
    assert profile_json(profile) == text


def test_translation_through_the_old_layout_is_unambiguous() -> None:
    translated: set[tuple[str, ...]] = {
        tuple(sorted(OLD_CODES[i] for i in range(10) if chord >> i & 1)) for chord in LAPTOP_OLD_BLOCKED
    }
    assert translated == set(EXPECTED)
    profile: KeyboardProfile = read_profile((FOLDER / "laptop-vn.json").read_text(encoding="utf-8"))
    assert {b.keys for b in profile.blocked} == translated


def test_laptop_vn_does_not_cover_qwerty_vm() -> None:
    profile: KeyboardProfile = read_profile((FOLDER / "laptop-vn.json").read_text(encoding="utf-8"))
    with pytest.raises(KeyboardError, match="KeyM"):
        finger_blocked(profile, VM)

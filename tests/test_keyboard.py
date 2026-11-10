"""Checks 8-14: calibration log, profile in key codes, profile file, blocked fingers, availability."""

import hashlib
import json
from typing import Any

import pytest

from steno_zero.chords import allowed_chords
from steno_zero.keyboard import (
    Blocked,
    CalibrationAttempt,
    CalibrationLog,
    KeyboardError,
    KeyboardProfile,
    available_chords,
    build_profile,
    calibration_chords,
    finger_blocked,
    is_available,
    keys_label,
    profile_json,
    profile_sha256,
    read_calibration_log,
    read_profile,
)
from steno_zero.layout import Layout
from tests.keyboard_helpers import (
    CHECK5,
    CHECK5_BLOCKED,
    CHECK5_SWAPPED,
    P1,
    P2,
    STARTED,
    VM_SORTED,
    calibration_dict,
    calibration_text,
    combos,
    count_available,
    profile_dict,
)
from tests.layout_helpers import KL_SWAPPED, SPACE, SWAPPED, VM


def test_calibration_chords() -> None:
    chords: tuple[int, ...] = calibration_chords()
    assert len(chords) == 165
    assert list(chords) == combos()


def test_read_calibration_log_ok() -> None:
    log: CalibrationLog = read_calibration_log(calibration_text())
    assert log.session == "calibration-2026-11-10T09-00-00.000Z"
    assert log.started == STARTED
    assert log.finished == "2026-11-10T09:06:00.000Z"
    assert log.user_agent == "pytest"
    assert log.max_held == 3
    assert log.layout == VM
    assert len(log.attempts) == 165
    assert isinstance(log.attempts, tuple)
    assert log.attempts[0] == CalibrationAttempt(3, 3, 0.0, 50.5)
    assert log.attempts[1] == CalibrationAttempt(5, 5, 100.0, 150.5)


def mutated(key: str, value: object) -> str:
    obj: dict[str, Any] = calibration_dict()
    obj[key] = value
    return json.dumps(obj)


def with_attempt(**changes: object) -> str:
    obj: dict[str, Any] = calibration_dict()
    obj["attempts"][0].update(changes)
    return json.dumps(obj)


def without(key: str) -> str:
    obj: dict[str, Any] = calibration_dict()
    del obj[key]
    return json.dumps(obj)


def short_layout() -> str:
    obj: dict[str, Any] = calibration_dict()
    obj["layout"]["keys"] = obj["layout"]["keys"][:9]
    return json.dumps(obj)


BAD_LOGS: dict[str, str] = {
    "not json": "{nope",
    "not an object": "[]",
    "foreign format": mutated("format", "steno-zero/trainer-log"),
    "foreign version": mutated("version", 3),
    "session empty": mutated("session", ""),
    "started not a string": mutated("started", None),
    "max_held too big": mutated("max_held", 11),
    "no layout": without("layout"),
    "layout of nine keys": short_layout(),
    "layout not an object": mutated("layout", "qwerty-vm"),
    "attempts empty": mutated("attempts", []),
    "target of four keys": with_attempt(target=15),
    "target of one key": with_attempt(target=1),
    "typed zero": with_attempt(typed=0),
    "typed too big": with_attempt(typed=1024),
    "down after up": with_attempt(down_ms=500.0, up_ms=100.0),
}


@pytest.mark.parametrize("name", sorted(BAD_LOGS))
def test_read_calibration_log_rejects(name: str) -> None:
    with pytest.raises(KeyboardError):
        read_calibration_log(BAD_LOGS[name])


def test_read_calibration_log_version_1_is_no_longer_read() -> None:
    with pytest.raises(KeyboardError, match="version 1 is no longer read"):
        read_calibration_log(mutated("version", 1))


def build(
    overrides: dict[int, list[int]] | None = None, name: str = "test", layout: Layout = VM
) -> KeyboardProfile:
    return build_profile(read_calibration_log(calibration_text(overrides, layout)), name)


def test_build_profile_check5_in_codes() -> None:
    profile: KeyboardProfile = build(CHECK5)
    assert profile.keys == tuple(sorted(VM.codes))
    assert profile.blocked == (
        Blocked(("KeyA", "KeyD", "KeyS"), True),
        Blocked(("KeyF", "KeyK", "KeyV"), False),
    )
    assert profile.name == "test"
    assert profile.session == "calibration-2026-11-10T09-00-00.000Z"
    assert profile.created == STARTED


def test_build_profile_swapped_fingers_give_the_same_physical_blocks() -> None:
    profile: KeyboardProfile = build(CHECK5_SWAPPED, layout=SWAPPED)
    assert profile.keys == tuple(sorted(SWAPPED.codes))
    assert profile.blocked == CHECK5_BLOCKED
    assert profile.blocked == build(CHECK5).blocked


def test_build_profile_all_pass_gives_empty_blocked() -> None:
    assert build().blocked == ()


def test_build_profile_keeps_only_minimal_blocked() -> None:
    overrides: dict[int, list[int]] = {3: [1, 1, 1]}
    c: int
    for c in combos():
        if c.bit_count() == 3 and c & 3 == 3:
            overrides[c] = [c & ~2, c & ~2, c & ~2]
    assert build(overrides).blocked == (Blocked(("KeyA", "KeyS"), False),)


def test_build_profile_blocked_sorted_by_length_then_keys() -> None:
    profile: KeyboardProfile = build({896: [128, 128, 128], 152: [8, 8, 8], 3: [1, 1, 1]})
    assert [b.keys for b in profile.blocked] == [
        ("KeyA", "KeyS"),
        ("KeyF", "KeyK", "KeyV"),
        ("KeyK", "KeyL", "Semicolon"),
    ]


def test_build_profile_unclear_needs_an_extra_key_not_just_a_missing_one() -> None:
    profile: KeyboardProfile = build({7: [3, 3, 3], 152: [24, 24, 25 | 128]})
    assert profile.blocked == (
        Blocked(("KeyA", "KeyD", "KeyS"), False),
        Blocked(("KeyF", "KeyK", "KeyV"), True),
    )


def test_build_profile_incomplete() -> None:
    obj: dict[str, Any] = calibration_dict()
    obj["attempts"] = obj["attempts"][1:]
    with pytest.raises(KeyboardError, match="incomplete"):
        build_profile(read_calibration_log(json.dumps(obj)), "test")
    with pytest.raises(KeyboardError, match="incomplete"):
        build({152: [24, 24]})


@pytest.mark.parametrize("name", ["Laptop", "", "lap top", "lap_top", "ноут", "a.b"])
def test_build_profile_rejects_bad_name(name: str) -> None:
    with pytest.raises(KeyboardError):
        build(name=name)


@pytest.mark.parametrize("name", ["laptop", "a-1", "0"])
def test_build_profile_accepts_good_name(name: str) -> None:
    assert build(name=name).name == name


def test_profile_json_exact_text() -> None:
    profile: KeyboardProfile = build(CHECK5)
    expected: dict[str, Any] = profile_dict(
        [(("KeyA", "KeyD", "KeyS"), True), (("KeyF", "KeyK", "KeyV"), False)]
    )
    assert profile_json(profile) == json.dumps(expected, ensure_ascii=False, indent=1) + "\n"
    obj: dict[str, Any] = json.loads(profile_json(profile))
    assert obj["version"] == 2
    assert obj["keys"] == list(VM_SORTED)
    assert all(set(b) == {"keys", "unclear"} for b in obj["blocked"])
    assert "user_agent" not in obj
    assert "layout" not in obj


def test_profile_round_trip() -> None:
    profile: KeyboardProfile = build(CHECK5)
    assert read_profile(profile_json(profile)) == profile
    assert read_profile(profile_json(P1)) == P1
    assert read_profile(profile_json(P2)) == P2


def test_profile_sha256_is_hash_of_canonical_text() -> None:
    assert profile_sha256(P1) == hashlib.sha256(profile_json(P1).encode("utf-8")).hexdigest()
    assert profile_sha256(P1) != profile_sha256(P2)
    reformatted: str = json.dumps(json.loads(profile_json(P1)), indent=4)
    assert profile_sha256(read_profile(reformatted)) == profile_sha256(P1)


def edited(**changes: object) -> str:
    obj: dict[str, Any] = profile_dict([(("KeyA", "KeyD", "KeyS"), True), (("KeyF", "KeyK", "KeyV"), False)])
    obj.update(changes)
    return json.dumps(obj)


def with_blocked(blocked: list[object]) -> str:
    return edited(blocked=blocked)


BAD_PROFILES: dict[str, str] = {
    "foreign format": edited(format="steno-zero/drill-log"),
    "version 1": edited(version=1),
    "version 3": edited(version=3),
    "name uppercase": edited(name="Laptop"),
    "keys unsorted": edited(keys=["KeyS", "KeyA", *VM_SORTED[2:]]),
    "keys repeated": edited(keys=["KeyA", "KeyA", *VM_SORTED[2:]]),
    "keys one code": edited(keys=["KeyA"]),
    "keys with a bad code": edited(keys=["Key A", *VM_SORTED[1:]]),
    "blocked code outside keys": with_blocked([{"keys": ["KeyA", "KeyN"], "unclear": False}]),
    "blocked of one code": with_blocked([{"keys": ["KeyA"], "unclear": False}]),
    "blocked codes unsorted": with_blocked([{"keys": ["KeyD", "KeyA"], "unclear": False}]),
    "blocked unsorted between items": with_blocked(
        [
            {"keys": ["KeyF", "KeyK", "KeyV"], "unclear": False},
            {"keys": ["KeyA", "KeyD", "KeyS"], "unclear": False},
        ]
    ),
    "longer before shorter": with_blocked(
        [
            {"keys": ["KeyA", "KeyD", "KeyS"], "unclear": False},
            {"keys": ["KeyF", "KeyK"], "unclear": False},
        ]
    ),
    "repeated block": with_blocked(
        [
            {"keys": ["KeyA", "KeyD"], "unclear": False},
            {"keys": ["KeyA", "KeyD"], "unclear": False},
        ]
    ),
    "block contains another": with_blocked(
        [
            {"keys": ["KeyA", "KeyD"], "unclear": False},
            {"keys": ["KeyA", "KeyD", "KeyS"], "unclear": False},
        ]
    ),
    "unclear a string": with_blocked([{"keys": ["KeyA", "KeyD"], "unclear": "no"}]),
    "unclear an int": with_blocked([{"keys": ["KeyA", "KeyD"], "unclear": 1}]),
    "no unclear": with_blocked([{"keys": ["KeyA", "KeyD"]}]),
    "no keys in a block": with_blocked([{"unclear": False}]),
    "not json": "{",
}


@pytest.mark.parametrize("name", sorted(BAD_PROFILES))
def test_read_profile_rejects(name: str) -> None:
    with pytest.raises(KeyboardError):
        read_profile(BAD_PROFILES[name])


def test_read_profile_version_1_is_no_longer_read() -> None:
    with pytest.raises(KeyboardError, match="version 1 is no longer read"):
        read_profile(edited(version=1))


def test_read_profile_accepts_four_codes_and_empty() -> None:
    four: KeyboardProfile = read_profile(
        json.dumps(profile_dict([(("KeyA", "KeyD", "KeyF", "KeyS"), False)]))
    )
    assert four.blocked == (Blocked(("KeyA", "KeyD", "KeyF", "KeyS"), False),)
    assert read_profile(json.dumps(profile_dict([]))).blocked == ()


def test_finger_blocked_on_qwerty_vm() -> None:
    assert finger_blocked(P1, VM) == (152,)
    assert finger_blocked(P2, VM) == (7, 896)


def test_finger_blocked_follows_the_layout() -> None:
    assert finger_blocked(P1, KL_SWAPPED) == (280,)
    assert finger_blocked(P1, SWAPPED) == (28,)


def test_finger_blocked_is_sorted() -> None:
    profile: KeyboardProfile = KeyboardProfile(
        "t", "c", STARTED, VM_SORTED, (Blocked(("KeyA", "KeyM"), False), Blocked(("KeyD", "KeyF"), False))
    )
    assert finger_blocked(profile, VM) == (12, 33)


def test_finger_blocked_skips_blocks_outside_the_layout() -> None:
    extra: tuple[str, ...] = tuple(sorted({*VM_SORTED, "KeyN"}))
    profile: KeyboardProfile = KeyboardProfile(
        "t",
        "c",
        STARTED,
        extra,
        (Blocked(("KeyD", "KeyN", "KeyV"), True), Blocked(("KeyF", "KeyK", "KeyV"), True)),
    )
    assert finger_blocked(profile, VM) == (152,)


def test_finger_blocked_needs_every_code_calibrated() -> None:
    info: pytest.ExceptionInfo[KeyboardError]
    with pytest.raises(KeyboardError, match="not calibrated:") as info:
        finger_blocked(P1, SPACE)
    assert "Space" in str(info.value)


@pytest.mark.parametrize(
    ("chord", "expected"), [(152, False), (153, False), (24, True), (88, True), (1023, False)]
)
def test_is_available_with_152_blocked(chord: int, expected: bool) -> None:
    assert is_available(chord, (152,)) is expected


@pytest.mark.parametrize("chord", [0, 1024, -1])
def test_is_available_rejects_bad_chord(chord: int) -> None:
    with pytest.raises(ValueError):
        is_available(chord, ())


def test_is_available_without_blocks_and_over_all_chords() -> None:
    assert is_available(1023, ())
    c: int
    for c in range(1, 1024):
        assert is_available(c, (7, 896)) == (c & 7 != 7 and c & 896 != 896)


def test_available_chords_counts() -> None:
    assert len(available_chords(6, ())) == 847
    assert available_chords(6, ()) == allowed_chords(6)
    assert len(available_chords(6, (152,))) == 783
    assert 152 not in available_chords(6, (152,))
    assert 88 in available_chords(6, (152,))
    assert len(available_chords(4, (7, 896))) == count_available(4, (7, 896))


def test_available_chords_sorted_and_filtered() -> None:
    chords: tuple[int, ...] = available_chords(6, (7, 896))
    assert list(chords) == sorted(chords)
    assert chords == tuple(c for c in allowed_chords(6) if c & 7 != 7 and c & 896 != 896)


def test_available_chords_bad_max_keys() -> None:
    with pytest.raises(ValueError):
        available_chords(1, ())


def test_keys_label() -> None:
    assert keys_label(("KeyF", "KeyK", "KeyV")) == "KeyF+KeyK+KeyV"

"""Checks 3-10: calibration chords, calibration log, profile building, profile file, availability."""

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
    is_available,
    profile_json,
    profile_sha256,
    read_calibration_log,
    read_profile,
)
from tests.keyboard_helpers import (
    CHECK5,
    P1,
    P2,
    STARTED,
    calibration_dict,
    calibration_text,
    combos,
    profile_dict,
)


def test_calibration_chords() -> None:
    chords: tuple[int, ...] = calibration_chords()
    assert len(chords) == 165
    assert all(c.bit_count() == 2 for c in chords[:45])
    assert list(chords[:45]) == sorted(chords[:45])
    assert all(c.bit_count() == 3 for c in chords[45:])
    assert list(chords[45:]) == sorted(chords[45:])
    assert len(set(chords)) == 165
    assert list(chords) == combos()


def test_read_calibration_log_ok() -> None:
    log: CalibrationLog = read_calibration_log(calibration_text())
    assert log.session == "calibration-2026-11-10T09-00-00.000Z"
    assert log.started == STARTED
    assert log.finished == "2026-11-10T09:06:00.000Z"
    assert log.user_agent == "pytest"
    assert log.max_held == 3
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


BAD_LOGS: dict[str, str] = {
    "not json": "{nope",
    "not an object": "[]",
    "foreign format": mutated("format", "steno-zero/trainer-log"),
    "foreign version": mutated("version", 2),
    "session not a string": mutated("session", 5),
    "session empty": mutated("session", ""),
    "started not a string": mutated("started", None),
    "finished not a string": mutated("finished", 1),
    "user_agent not a string": mutated("user_agent", []),
    "max_held too big": mutated("max_held", 11),
    "max_held negative": mutated("max_held", -1),
    "max_held a string": mutated("max_held", "3"),
    "max_held a float": mutated("max_held", 3.5),
    "attempts empty": mutated("attempts", []),
    "attempts not a list": mutated("attempts", {}),
    "target of four keys": with_attempt(target=15),
    "target of one key": with_attempt(target=1),
    "target zero": with_attempt(target=0),
    "typed zero": with_attempt(typed=0),
    "typed too big": with_attempt(typed=1024),
    "typed a string": with_attempt(typed="3"),
    "typed a float": with_attempt(typed=3.5),
    "down after up": with_attempt(down_ms=500.0, up_ms=100.0),
    "negative down": with_attempt(down_ms=-1.0, up_ms=10.0),
    "time a string": with_attempt(down_ms="1"),
    "time a bool": with_attempt(down_ms=True, up_ms=5.0),
}


@pytest.mark.parametrize("name", sorted(BAD_LOGS))
def test_read_calibration_log_rejects(name: str) -> None:
    with pytest.raises(KeyboardError):
        read_calibration_log(BAD_LOGS[name])


def build(overrides: dict[int, list[int]] | None = None, name: str = "test") -> KeyboardProfile:
    return build_profile(read_calibration_log(calibration_text(overrides)), name)


def test_build_profile_check5() -> None:
    profile: KeyboardProfile = build(CHECK5)
    assert profile.blocked == (Blocked(7, True), Blocked(152, False))
    assert is_available(24, profile)
    assert profile.name == "test"
    assert profile.session == "calibration-2026-11-10T09-00-00.000Z"
    assert profile.created == STARTED


def test_build_profile_all_pass_gives_empty_blocked() -> None:
    assert build().blocked == ()


def test_build_profile_keeps_only_minimal_blocked() -> None:
    overrides: dict[int, list[int]] = {3: [1, 1, 1]}
    c: int
    for c in combos():
        if c.bit_count() == 3 and c & 3 == 3:
            overrides[c] = [c & ~2, c & ~2, c & ~2]
    profile: KeyboardProfile = build(overrides)
    assert profile.blocked == (Blocked(3, False),)


def test_build_profile_blocked_sorted_ascending() -> None:
    profile: KeyboardProfile = build({896: [128, 128, 128], 7: [1, 1, 1], 152: [8, 8, 8]})
    assert [b.chord for b in profile.blocked] == [7, 152, 896]


def test_build_profile_unclear_needs_an_extra_key_not_just_a_missing_one() -> None:
    profile: KeyboardProfile = build({7: [3, 3, 3], 152: [24, 24, 25 | 128]})
    assert profile.blocked == (Blocked(7, False), Blocked(152, True))


def test_build_profile_incomplete_missing_combination() -> None:
    obj: dict[str, Any] = calibration_dict()
    obj["attempts"] = obj["attempts"][1:]
    with pytest.raises(KeyboardError, match="incomplete"):
        build_profile(read_calibration_log(json.dumps(obj)), "test")


def test_build_profile_incomplete_two_failed_attempts() -> None:
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
    expected: dict[str, Any] = profile_dict([(7, True), (152, False)])
    assert profile_json(profile) == json.dumps(expected, ensure_ascii=False, indent=1) + "\n"
    assert "user_agent" not in profile_json(profile)
    assert json.loads(profile_json(profile))["blocked"][1]["label"] == "f v k"


def test_profile_round_trip() -> None:
    profile: KeyboardProfile = build(CHECK5)
    assert read_profile(profile_json(profile)) == profile
    assert read_profile(profile_json(P1)) == P1


def test_profile_sha256_is_hash_of_canonical_text() -> None:
    assert profile_sha256(P1) == hashlib.sha256(profile_json(P1).encode("utf-8")).hexdigest()


def test_profile_sha256_ignores_formatting_but_not_content() -> None:
    profile: KeyboardProfile = build(CHECK5)
    reformatted: str = json.dumps(json.loads(profile_json(profile)), indent=4)
    assert profile_sha256(read_profile(reformatted)) == profile_sha256(profile)
    other: KeyboardProfile = KeyboardProfile(
        profile.name, profile.session, profile.created, (*profile.blocked, Blocked(896, False))
    )
    assert profile_sha256(other) != profile_sha256(profile)
    assert profile_sha256(P1) != profile_sha256(P2)


def edited(**changes: object) -> str:
    obj: dict[str, Any] = profile_dict([(7, True), (152, False)])
    obj.update(changes)
    return json.dumps(obj)


def with_blocked(blocked: list[object]) -> str:
    return edited(blocked=blocked)


BAD_PROFILES: dict[str, str] = {
    "foreign format": edited(format="steno-zero/drill-log"),
    "foreign version": edited(version=2),
    "name uppercase": edited(name="Laptop"),
    "session not a string": edited(session=1),
    "created not a string": edited(created=None),
    "wrong label": with_blocked([{"chord": 152, "label": "a s d", "unclear": False}]),
    "one key": with_blocked([{"chord": 1, "label": "a", "unclear": False}]),
    "chord out of range": with_blocked([{"chord": 1024, "label": "x", "unclear": False}]),
    "chord not an int": with_blocked([{"chord": "7", "label": "a s d", "unclear": False}]),
    "unsorted": with_blocked(
        [
            {"chord": 152, "label": "f v k", "unclear": False},
            {"chord": 7, "label": "a s d", "unclear": False},
        ]
    ),
    "repeat": with_blocked(
        [
            {"chord": 7, "label": "a s d", "unclear": False},
            {"chord": 7, "label": "a s d", "unclear": False},
        ]
    ),
    "superset": with_blocked(
        [
            {"chord": 7, "label": "a s d", "unclear": False},
            {"chord": 15, "label": "a s d f", "unclear": False},
        ]
    ),
    "unclear a string": with_blocked([{"chord": 7, "label": "a s d", "unclear": "no"}]),
    "unclear an int": with_blocked([{"chord": 7, "label": "a s d", "unclear": 1}]),
    "no unclear field": with_blocked([{"chord": 7, "label": "a s d"}]),
    "no label field": with_blocked([{"chord": 7, "unclear": False}]),
    "no chord field": with_blocked([{"label": "a s d", "unclear": False}]),
    "not json": "{",
}


@pytest.mark.parametrize("name", sorted(BAD_PROFILES))
def test_read_profile_rejects(name: str) -> None:
    with pytest.raises(KeyboardError):
        read_profile(BAD_PROFILES[name])


def test_read_profile_accepts_four_keys_and_empty() -> None:
    four: KeyboardProfile = read_profile(json.dumps(profile_dict([(15, False)])))
    assert four.blocked == (Blocked(15, False),)
    empty: KeyboardProfile = read_profile(json.dumps(profile_dict([])))
    assert empty.blocked == ()


def test_is_available_p1() -> None:
    assert not is_available(152, P1)
    assert not is_available(152 | 1, P1)
    assert is_available(8 | 16 | 64, P1)
    assert is_available(24, P1)


def test_is_available_without_profile() -> None:
    assert is_available(152, None)
    assert is_available(1023, None)


@pytest.mark.parametrize("chord", [0, 1024, -1])
def test_is_available_rejects_bad_chord(chord: int) -> None:
    with pytest.raises(ValueError):
        is_available(chord, P1)
    with pytest.raises(ValueError):
        is_available(chord, None)


def test_available_chords_counts() -> None:
    assert len(available_chords(6, P1)) == 783
    assert len(available_chords(6, None)) == 847
    assert available_chords(6, None) == allowed_chords(6)
    assert 152 not in available_chords(6, P1)
    assert 88 in available_chords(6, P1)


def test_available_chords_sorted_and_filtered() -> None:
    chords: tuple[int, ...] = available_chords(6, P2)
    assert list(chords) == sorted(chords)
    assert chords == tuple(c for c in allowed_chords(6) if is_available(c, P2))


def test_is_available_p2_over_all_chords() -> None:
    c: int
    for c in range(1, 1024):
        assert is_available(c, P2) == (c & 7 != 7 and c & 896 != 896)


def test_available_chords_bad_max_keys() -> None:
    with pytest.raises(ValueError):
        available_chords(1, None)

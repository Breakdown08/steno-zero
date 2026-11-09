"""Checks 22-24: the log of random chords."""

import copy
import json
from typing import Any

import pytest

from steno_zero.drill import DrillLog, DrillLogError, Presentation, read_drill_log
from steno_zero.trainer import TrainerLogError, read_trainer_log
from tests.drill_helpers import SHA, drill_dict, drill_text
from tests.keyboard_helpers import calibration_text
from tests.trainer_helpers import example_text


def test_example_log_reads() -> None:
    log: DrillLog = read_drill_log(drill_text())
    assert log.keyboard == ("laptop", SHA)
    assert log.session == "drill-7-2026-11-10T09-00-00.000Z"
    assert (log.seed, log.block, log.max_keys, log.max_held) == (0, 7, 6, 6)
    assert log.started == "2026-11-10T09:00:00.000Z"
    assert log.finished == "2026-11-10T09:03:12.400Z"
    assert log.user_agent == "pytest"
    assert log.presentations == (
        Presentation(0, 17, 17, 1000.0, 1450.2, 1610.7),
        Presentation(1, 3, 7, 1625.0, 2100.0, 2230.5),
    )


def test_log_without_keyboard() -> None:
    obj: dict[str, Any] = drill_dict()
    obj["keyboard"] = None
    assert read_drill_log(json.dumps(obj)).keyboard is None


def edited(**changes: object) -> str:
    obj: dict[str, Any] = drill_dict()
    obj.update(changes)
    return json.dumps(obj)


def with_row(**changes: object) -> str:
    obj: dict[str, Any] = drill_dict()
    obj["presentations"][1].update(changes)
    return json.dumps(obj)


def without_field(name: str) -> str:
    obj: dict[str, Any] = drill_dict()
    del obj["presentations"][0][name]
    return json.dumps(obj)


def row(i: int, shown: float, down: float, up: float) -> dict[str, Any]:
    return {"i": i, "target": 17, "typed": 17, "shown_ms": shown, "down_ms": down, "up_ms": up}


BAD_LOGS: dict[str, str] = {
    "not json": "{",
    "not an object": "[1]",
    "foreign format": edited(format="steno-zero/trainer-log"),
    "foreign version": edited(version=2),
    "session not a string": edited(session=3),
    "session empty": edited(session=""),
    "started not a string": edited(started=1),
    "finished not a string": edited(finished=None),
    "user_agent not a string": edited(user_agent=1),
    "seed a bool": edited(seed=True),
    "seed a string": edited(seed="0"),
    "block negative": edited(block=-1),
    "block a float": edited(block=1.5),
    "max_keys one": edited(max_keys=1),
    "max_keys eleven": edited(max_keys=11),
    "max_held eleven": edited(max_held=11),
    "keyboard a string": edited(keyboard="laptop"),
    "keyboard sha of 63 characters": edited(keyboard={"name": "laptop", "sha256": SHA[:63]}),
    "keyboard sha uppercase": edited(keyboard={"name": "laptop", "sha256": SHA.upper()}),
    "keyboard sha not hex": edited(keyboard={"name": "laptop", "sha256": "g" * 64}),
    "keyboard name A": edited(keyboard={"name": "A", "sha256": SHA}),
    "keyboard without name": edited(keyboard={"sha256": SHA}),
    "presentations empty": edited(presentations=[]),
    "presentations not a list": edited(presentations={}),
    "target of seven keys": with_row(target=127),
    "target zero": with_row(target=0),
    "target 1024": with_row(target=1024),
    "typed zero": with_row(typed=0),
    "typed 1024": with_row(typed=1024),
    "i skipped": with_row(i=2),
    "i repeated": with_row(i=0),
    "shown before previous up": with_row(shown_ms=1600.0),
    "shown after down": with_row(shown_ms=2200.0),
    "down after up": with_row(down_ms=2300.0),
    "negative shown": edited(presentations=[row(0, -1.0, 5.0, 9.0)]),
    "true in time": with_row(shown_ms=True),
    "time a string": with_row(up_ms="2230.5"),
    "no target": without_field("target"),
    "no up_ms": without_field("up_ms"),
}


@pytest.mark.parametrize("name", sorted(BAD_LOGS))
def test_log_rejects(name: str) -> None:
    with pytest.raises(DrillLogError):
        read_drill_log(BAD_LOGS[name])


def test_max_keys_limits_the_target() -> None:
    obj: dict[str, Any] = copy.deepcopy(drill_dict())
    obj["max_keys"] = 2
    obj["presentations"][0]["target"] = 7
    with pytest.raises(DrillLogError):
        read_drill_log(json.dumps(obj))


def test_foreign_logs_are_not_drill_logs_and_the_other_way_round() -> None:
    with pytest.raises(DrillLogError):
        read_drill_log(example_text())
    with pytest.raises(DrillLogError):
        read_drill_log(calibration_text())
    with pytest.raises(TrainerLogError):
        read_trainer_log(drill_text())

"""Checks 24-26: the log of random chords."""

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from steno_zero.drill import DrillLog, DrillLogError, Presentation, read_drill_log
from steno_zero.trainer import TrainerLogError, read_trainer_log
from tests.drill_helpers import SHA, drill_dict, drill_text
from tests.helpers import ROOT
from tests.keyboard_helpers import calibration_text
from tests.layout_helpers import VM
from tests.trainer_helpers import example_text


def test_example_log_reads() -> None:
    log: DrillLog = read_drill_log(drill_text())
    assert log.layout == VM
    assert log.layout.codes[5] == "KeyM"
    assert log.keyboard == ("laptop-vm", SHA)
    assert log.session == "drill-7-2026-11-10T09-00-00.000Z"
    assert (log.seed, log.block, log.max_keys, log.max_held) == (0, 7, 6, 6)
    assert log.started == "2026-11-10T09:00:00.000Z"
    assert log.finished == "2026-11-10T09:03:12.400Z"
    assert log.user_agent == "pytest"
    assert log.presentations[1].i == 2
    assert log.presentations == (
        Presentation(0, 17, 17, 1000.0, 1450.2, 1610.7),
        Presentation(2, 3, 7, 1625.0, 2100.0, 2230.5),
    )


def test_log_without_keyboard() -> None:
    obj: dict[str, Any] = drill_dict()
    obj["keyboard"] = None
    assert read_drill_log(json.dumps(obj)).keyboard is None


def test_first_i_may_be_positive_and_gaps_are_allowed() -> None:
    rows: list[dict[str, Any]] = [
        {"i": 5, "target": 17, "typed": 17, "shown_ms": 1.0, "down_ms": 5.0, "up_ms": 9.0},
        {"i": 9, "target": 17, "typed": 17, "shown_ms": 20.0, "down_ms": 25.0, "up_ms": 29.0},
    ]
    log: DrillLog = read_drill_log(json.dumps(drill_dict(rows)))
    assert [p.i for p in log.presentations] == [5, 9]


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


def without_layout() -> str:
    obj: dict[str, Any] = drill_dict()
    del obj["layout"]
    return json.dumps(obj)


def nine_keys() -> str:
    obj: dict[str, Any] = drill_dict()
    obj["layout"]["keys"] = obj["layout"]["keys"][:9]
    return json.dumps(obj)


def row(i: int, shown: float, down: float, up: float) -> dict[str, Any]:
    return {"i": i, "target": 17, "typed": 17, "shown_ms": shown, "down_ms": down, "up_ms": up}


BAD_LOGS: dict[str, str] = {
    "not json": "{",
    "not an object": "[1]",
    "foreign format": edited(format="steno-zero/trainer-log"),
    "foreign version": edited(version=3),
    "session empty": edited(session=""),
    "seed a bool": edited(seed=True),
    "block negative": edited(block=-1),
    "max_keys eleven": edited(max_keys=11),
    "no layout": without_layout(),
    "layout of nine keys": nine_keys(),
    "layout a string": edited(layout="qwerty-vm"),
    "keyboard a string": edited(keyboard="laptop"),
    "keyboard sha of 63 characters": edited(keyboard={"name": "laptop", "sha256": SHA[:63]}),
    "keyboard name A": edited(keyboard={"name": "A", "sha256": SHA}),
    "presentations empty": edited(presentations=[]),
    "target of seven keys": with_row(target=127),
    "target zero": with_row(target=0),
    "typed 1024": with_row(typed=1024),
    "i repeated": with_row(i=0),
    "i decreasing": edited(presentations=[row(2, 1.0, 5.0, 9.0), row(1, 20.0, 25.0, 29.0)]),
    "i negative": edited(presentations=[row(-1, 1.0, 5.0, 9.0)]),
    "i a float": with_row(i=2.0),
    "shown before previous up": with_row(shown_ms=1600.0),
    "down after up": with_row(down_ms=2300.0),
    "time a string": with_row(up_ms="2230.5"),
    "no target": without_field("target"),
}


@pytest.mark.parametrize("name", sorted(BAD_LOGS))
def test_log_rejects(name: str) -> None:
    with pytest.raises(DrillLogError):
        read_drill_log(BAD_LOGS[name])


def test_version_1_is_no_longer_read() -> None:
    obj: dict[str, Any] = drill_dict()
    obj["version"] = 1
    del obj["layout"]
    with pytest.raises(DrillLogError, match="version 1 is no longer read"):
        read_drill_log(json.dumps(obj))


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


def test_the_trial_log_of_the_first_release_is_rejected() -> None:
    trial: Path = ROOT / "runs" / "drill" / "steno-zero-drill-27-2026-11-09T10-06-05.091Z.json"
    if not trial.is_file():
        pytest.skip("runs/ is not in git; the trial log is not here")
    with pytest.raises(DrillLogError, match="version 1 is no longer read"):
        read_drill_log(trial.read_text(encoding="utf-8"))

"""Checks 1-3: finger names, chord labels, no key codes in the code."""

import re
from pathlib import Path

import pytest

import steno_zero.trainer as trainer
from steno_zero.chords import FINGERS, N_KEYS, chord_keys
from steno_zero.trainer import chord_label
from tests.helpers import ROOT
from tests.layout_helpers import FINGER_NAMES, VM_CODES

ALL: str = " ".join(FINGER_NAMES)


def test_fingers_constant() -> None:
    assert FINGERS == ("L4", "L3", "L2", "L1", "L0", "R0", "R1", "R2", "R3", "R4")
    assert len(FINGERS) == N_KEYS


@pytest.mark.parametrize(
    ("chord", "label"), [(1, "L4"), (8, "L1"), (72, "L1 R1"), (48, "L0 R0"), (1023, ALL)]
)
def test_chord_label_examples(chord: int, label: str) -> None:
    assert chord_label(chord) == label


def test_chord_label_matches_chord_keys_for_every_chord() -> None:
    bad: list[int] = [
        c for c in range(1, 1024) if chord_label(c).split(" ") != [FINGER_NAMES[i] for i in chord_keys(c)]
    ]
    assert bad == []


@pytest.mark.parametrize("chord", [0, 1024])
def test_chord_label_out_of_range(chord: int) -> None:
    with pytest.raises(ValueError):
        chord_label(chord)


def test_trainer_does_not_export_key_codes_or_labels() -> None:
    assert not hasattr(trainer, "KEY_CODES")
    assert not hasattr(trainer, "KEY_LABELS")
    assert trainer.HELP_KEY == "Slash"


def test_no_key_code_of_the_layout_in_the_python_sources() -> None:
    found: list[str] = []
    path: Path
    for path in sorted((ROOT / "src").rglob("*.py")):
        text: str = path.read_text(encoding="utf-8")
        code: str
        for code in VM_CODES:
            if re.search(rf"\b{code}\b", text):
                found.append(f"{path.name}: {code}")
    assert found == []

"""Checks 10-12: chords and costs."""

import pytest

from steno_zero.chords import chord_costs, chord_keys
from steno_zero.params import CostParams


def test_chord_keys() -> None:
    assert chord_keys(1) == (0,)
    assert chord_keys(72) == (3, 6)
    assert chord_keys(1023) == tuple(range(10))


@pytest.mark.parametrize("bad", [0, 1024])
def test_chord_keys_out_of_range(bad: int) -> None:
    with pytest.raises(ValueError):
        chord_keys(bad)


def test_chord_costs_values() -> None:
    costs: tuple[int, ...] = chord_costs(CostParams())
    assert len(costs) == 1024
    assert costs[0] == 0
    expected: dict[int, int] = {1: 240, 2: 225, 3: 295, 8: 200, 64: 200, 72: 230, 1023: 630}
    chord: int
    for chord in expected:
        assert costs[chord] == expected[chord], chord
    first: list[int] = sorted(range(1, 1024), key=lambda c: (costs[c], c))[:12]
    assert first == [8, 64, 4, 128, 16, 32, 2, 256, 72, 12, 68, 136]
    assert [costs[c] for c in first] == [200, 200, 205, 205, 210, 210, 225, 225, 230, 235, 235, 235]


def test_chord_costs_bad_params() -> None:
    with pytest.raises(ValueError):
        chord_costs(CostParams(finger_ms=(0,) * 9))
    with pytest.raises(ValueError):
        chord_costs(CostParams(finger_ms=(-1, 0, 0, 0, 0, 0, 0, 0, 0, 0)))

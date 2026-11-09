"""Checks 12-18: strata and the drill plan."""

import json
import subprocess
import sys
from collections import Counter

import pytest

from steno_zero.chords import allowed_chords
from steno_zero.drill import drill_plan, drill_strata
from steno_zero.keyboard import Blocked, KeyboardProfile, available_chords, is_available
from tests.drill_helpers import Plan, pair_chords, plan_default, plan_with, stratum_of
from tests.keyboard_helpers import P2

PAIRS_BLOCKED: KeyboardProfile = KeyboardProfile(
    "pairs", "c", "2026-11-10T00:00:00.000Z", tuple(Blocked(c, False) for c in pair_chords())
)


def test_strata_without_profile() -> None:
    strata: dict[tuple[int, int], tuple[int, ...]] = drill_strata(6)
    assert len(strata) == 25
    assert strata[(1, 1)] == (1, 2, 4, 8, 16)
    assert len(strata[(6, 3)]) == 100
    assert (6, 6) not in strata
    chords: list[int] = [c for group in strata.values() for c in group]
    assert sorted(chords) == list(allowed_chords(6))
    key: tuple[int, int]
    for key in strata:
        assert strata[key] != ()
        assert list(strata[key]) == sorted(strata[key])
        assert all(stratum_of(c) == key for c in strata[key])


def test_strata_with_profile() -> None:
    strata: dict[tuple[int, int], tuple[int, ...]] = drill_strata(6, P2)
    assert (5, 5) not in strata
    assert (5, 0) not in strata
    chords: list[int] = [c for group in strata.values() for c in group]
    assert sorted(chords) == list(available_chords(6, P2))


def test_strata_bad_max_keys() -> None:
    with pytest.raises(ValueError):
        drill_strata(1)


def test_plan_covers_every_chord() -> None:
    plan: Plan = plan_default()
    assert len(plan) == 100
    assert all(len(block) == 100 for block in plan)
    seen: set[int] = {c for block in plan for c in block}
    assert seen == set(allowed_chords(6))
    assert len(seen) == 847


def test_plan_with_profile_covers_every_available_chord() -> None:
    plan: Plan = plan_with(P2)
    seen: set[int] = {c for block in plan for c in block}
    assert all(is_available(c, P2) for c in seen)
    assert len(seen) == len(available_chords(6, P2))
    assert 31 not in seen
    assert 992 not in seen


def check_balance(plan: Plan, max_keys: int, profile: KeyboardProfile | None) -> None:
    strata: dict[tuple[int, int], tuple[int, ...]] = drill_strata(max_keys, profile)
    ns: set[int] = {n for n, _ in strata}
    block: tuple[int, ...]
    for block in plan:
        by_n: Counter[int] = Counter(c.bit_count() for c in block)
        assert set(by_n) <= ns
        counts: list[int] = [by_n[n] for n in ns]
        assert max(counts) - min(counts) <= 1, by_n
        n: int
        for n in ns:
            by_left: Counter[int] = Counter(stratum_of(c)[1] for c in block if c.bit_count() == n)
            lefts: list[int] = [left for m, left in strata if m == n]
            sub: list[int] = [by_left[left] for left in lefts]
            assert max(sub) - min(sub) <= 1, (n, by_left)


def test_balance_by_n_and_left_default() -> None:
    check_balance(plan_default(), 6, None)


def test_balance_by_n_and_left_with_profile() -> None:
    check_balance(plan_with(P2), 6, P2)


def test_balance_small_plan() -> None:
    check_balance(drill_plan(3, 5, 37, 4), 4, None)


def check_stratum_balance(plan: Plan, profile: KeyboardProfile | None) -> None:
    counts: Counter[int] = Counter(c for block in plan for c in block)
    key: tuple[int, int]
    group: tuple[int, ...]
    for key, group in drill_strata(6, profile).items():
        per_chord: list[int] = [counts[c] for c in group]
        assert max(per_chord) - min(per_chord) <= 1, key


def test_stratum_balance_default() -> None:
    check_stratum_balance(plan_default(), None)


def test_stratum_balance_with_profile() -> None:
    check_stratum_balance(plan_with(P2), P2)


def no_repeats(plan: Plan) -> bool:
    return all(a != b for block in plan for a, b in zip(block, block[1:], strict=False))


def test_no_repeats_in_a_row() -> None:
    assert no_repeats(plan_default())
    assert no_repeats(plan_with(P2))
    assert no_repeats(drill_plan(5, 20, 10, 2))


def test_plan_is_deterministic() -> None:
    assert drill_plan(0, 5, 20, 6) == drill_plan(0, 5, 20, 6)
    assert drill_plan(0, 5, 20, 6, None) == drill_plan(0, 5, 20, 6)
    assert drill_plan(1, 5, 20, 6) != drill_plan(0, 5, 20, 6)
    assert drill_plan(0, 5, 20, 6, P2) == drill_plan(0, 5, 20, 6, P2)


def test_plan_same_in_another_process() -> None:
    code: str = (
        "import json; from steno_zero.drill import drill_plan; print(json.dumps(drill_plan(7, 4, 30, 6)))"
    )
    out: str = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout
    assert json.loads(out) == [list(block) for block in drill_plan(7, 4, 30, 6)]


@pytest.mark.parametrize(
    ("blocks", "size", "max_keys"),
    [(0, 100, 6), (1, 5, 6), (1, 1001, 6), (1, 100, 11), (1, 100, 1), (-1, 100, 6)],
)
def test_plan_errors(blocks: int, size: int, max_keys: int) -> None:
    with pytest.raises(ValueError):
        drill_plan(0, blocks, size, max_keys)


def test_plan_with_all_pairs_blocked_has_only_single_keys() -> None:
    plan: Plan = drill_plan(0, 3, 20, 6, PAIRS_BLOCKED)
    assert len(plan) == 3
    assert all(len(block) == 20 for block in plan)
    assert {c for block in plan for c in block} <= {1, 2, 4, 8, 16, 32, 64, 128, 256, 512}
    assert no_repeats(plan)
    assert set(drill_strata(6, PAIRS_BLOCKED)) == {(1, 0), (1, 1)}

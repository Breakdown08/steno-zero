"""Checks 19, 28a: strata and the drill plan, with and without blocked chords."""

import json
import subprocess
import sys
from collections import Counter

import pytest

from steno_zero.chords import allowed_chords
from steno_zero.drill import drill_plan, drill_strata
from tests.drill_helpers import LAPTOP_OLD_BLOCKED, Plan, pair_chords, plan_default, plan_with, stratum_of
from tests.keyboard_helpers import P2_BLOCKED

PAIRS_BLOCKED: tuple[int, ...] = tuple(pair_chords())


def is_free(chord: int, blocked: tuple[int, ...]) -> bool:
    return not any(chord & b == b for b in blocked)


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


def test_strata_with_blocked() -> None:
    strata: dict[tuple[int, int], tuple[int, ...]] = drill_strata(6, P2_BLOCKED)
    assert (5, 5) not in strata
    assert (5, 0) not in strata
    chords: list[int] = [c for group in strata.values() for c in group]
    assert sorted(chords) == [c for c in allowed_chords(6) if is_free(c, P2_BLOCKED)]


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


def test_plan_with_blocked_covers_every_available_chord() -> None:
    plan: Plan = plan_with(P2_BLOCKED)
    seen: set[int] = {c for block in plan for c in block}
    assert all(is_free(c, P2_BLOCKED) for c in seen)
    assert len(seen) == len([c for c in allowed_chords(6) if is_free(c, P2_BLOCKED)])
    assert 31 not in seen
    assert 992 not in seen


def check_balance(plan: Plan, max_keys: int, blocked: tuple[int, ...]) -> None:
    strata: dict[tuple[int, int], tuple[int, ...]] = drill_strata(max_keys, blocked)
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
    check_balance(plan_default(), 6, ())


def test_balance_by_n_and_left_with_blocked() -> None:
    check_balance(plan_with(P2_BLOCKED), 6, P2_BLOCKED)


def test_balance_small_plan() -> None:
    check_balance(drill_plan(3, 5, 37, 4), 4, ())


def check_stratum_balance(plan: Plan, blocked: tuple[int, ...]) -> None:
    counts: Counter[int] = Counter(c for block in plan for c in block)
    key: tuple[int, int]
    group: tuple[int, ...]
    for key, group in drill_strata(6, blocked).items():
        per_chord: list[int] = [counts[c] for c in group]
        assert max(per_chord) - min(per_chord) <= 1, key


def test_stratum_balance_default() -> None:
    check_stratum_balance(plan_default(), ())


def test_stratum_balance_with_blocked() -> None:
    check_stratum_balance(plan_with(P2_BLOCKED), P2_BLOCKED)


def no_repeats(plan: Plan) -> bool:
    return all(a != b for block in plan for a, b in zip(block, block[1:], strict=False))


def test_no_repeats_in_a_row() -> None:
    assert no_repeats(plan_default())
    assert no_repeats(plan_with(P2_BLOCKED))
    assert no_repeats(drill_plan(5, 20, 10, 2))


def test_plan_is_deterministic() -> None:
    assert drill_plan(0, 5, 20, 6) == drill_plan(0, 5, 20, 6)
    assert drill_plan(0, 5, 20, 6, ()) == drill_plan(0, 5, 20, 6)
    assert drill_plan(1, 5, 20, 6) != drill_plan(0, 5, 20, 6)
    assert drill_plan(0, 5, 20, 6, P2_BLOCKED) == drill_plan(0, 5, 20, 6, P2_BLOCKED)
    assert drill_plan(0, 5, 20, 6, P2_BLOCKED) != drill_plan(0, 5, 20, 6)


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


def test_plan_for_the_migrated_laptop_blocks() -> None:
    blocked: tuple[int, ...] = LAPTOP_OLD_BLOCKED
    plan: Plan = drill_plan(0, 20, 100, 6, blocked)
    assert len(plan) == 20
    assert all(len(block) == 100 for block in plan)
    assert all(is_free(c, blocked) and 1 <= c.bit_count() <= 6 for block in plan for c in block)
    check_balance(plan, 6, blocked)
    assert no_repeats(plan)
    assert plan == drill_plan(0, 20, 100, 6, blocked)
    assert plan != drill_plan(1, 20, 100, 6, blocked)
    assert len(drill_strata(6, blocked)) <= 25
    assert {c for group in drill_strata(6, blocked).values() for c in group} == {
        c for c in allowed_chords(6) if is_free(c, blocked)
    }


def test_plan_without_blocks_equals_the_earlier_numbers() -> None:
    assert drill_plan(0, 2, 12, 6) == (
        (256, 804, 917, 76, 94, 533, 31, 18, 655, 800, 264, 16),
        (692, 30, 8, 512, 66, 11, 744, 20, 672, 57, 543, 1000),
    )
    assert drill_plan(7, 1, 8, 4) == ((26, 3, 27, 224, 1, 96, 128, 960),)

"""Chords on ten keys."""

from steno_zero.params import CostParams

N_KEYS: int = 10
N_CHORDS: int = 1023


def chord_keys(chord: int) -> tuple[int, ...]:
    if not 1 <= chord <= N_CHORDS:
        raise ValueError(f"chord out of range 1..{N_CHORDS}: {chord}")
    return tuple(i for i in range(N_KEYS) if chord >> i & 1)


def neighbours(chord: int) -> tuple[int, ...]:
    if not 1 <= chord <= N_CHORDS:
        raise ValueError(f"chord out of range 1..{N_CHORDS}: {chord}")
    return tuple(sorted(n for n in (chord ^ (1 << i) for i in range(N_KEYS)) if n >= 1))


def chord_costs(params: CostParams) -> tuple[int, ...]:
    if len(params.finger_ms) != N_KEYS:
        raise ValueError(f"finger_ms must have {N_KEYS} numbers")
    if any(v < 0 for v in params.finger_ms) or params.base_ms < 0 or params.extra_key_ms < 0:
        raise ValueError("costs must not be negative")
    costs: list[int] = [0]
    chord: int
    for chord in range(1, N_CHORDS + 1):
        keys: tuple[int, ...] = chord_keys(chord)
        costs.append(
            params.base_ms + params.extra_key_ms * (len(keys) - 1) + sum(params.finger_ms[k] for k in keys)
        )
    return tuple(costs)

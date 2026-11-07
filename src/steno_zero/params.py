"""Placeholder numbers: all defaults are stubs until Kirill measures real values."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CostParams:
    base_ms: int = 200
    extra_key_ms: int = 30
    finger_ms: tuple[int, ...] = (40, 25, 5, 0, 10, 10, 0, 5, 25, 40)


@dataclass(frozen=True)
class PenaltyParams:
    entry_s: float = 60.0
    rarity_s: float = 120.0
    rarity_uses: float = 50.0
    slip_prob: float = 0.002  # stub, not a measurement
    confusion_s: float = 2.0  # stub, not a measurement; 0 switches the penalty off


DEFAULT_HORIZON: float = 1_000_000.0
MAX_PIECE_LEN: int = 8

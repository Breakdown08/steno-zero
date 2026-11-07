"""Checks 7-9: alphabet and normalize."""

from steno_zero.alphabet import ALPHABET, normalize
from tests.helpers import fragment

SAMPLE: str = "Ко́злах — «Вот»… 1886 г.\n\nHello!"


def test_alphabet_shape() -> None:
    assert len(ALPHABET) == 41
    assert len(set(ALPHABET)) == 41
    assert "ё" in ALPHABET
    assert " " in ALPHABET


def test_normalize_example() -> None:
    assert normalize(SAMPLE) == "козлах - вот... г. !"


def test_normalize_idempotent_and_in_alphabet() -> None:
    s: str
    for s in (fragment(), SAMPLE):
        once: str = normalize(s)
        assert normalize(once) == once
        assert set(once) <= set(ALPHABET)
    assert normalize("ЁЖ") == "ёж"


def test_normalize_steps() -> None:
    assert normalize("а б\tв") == "а б в"
    assert normalize("  а   б  ") == "а б"
    assert normalize("а–б−в‑г") == "а-б-в-г"
    assert normalize("е ё") == "е ё"
    assert normalize("ё") != normalize("е")

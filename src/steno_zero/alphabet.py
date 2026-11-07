"""Alphabet and text normalisation."""

import unicodedata

ALPHABET: str = "абвгдеёжзийклмнопрстуфхцчшщъыьэюя -.,!?:;"

_ALLOWED: frozenset[str] = frozenset(ALPHABET)
_DASHES: dict[int, str] = {
    0x2014: "-",
    0x2013: "-",
    0x2011: "-",
    0x2212: "-",
    0x2026: "...",
    0x0301: "",
    0x0300: "",
}


def normalize(text: str) -> str:
    out: str = unicodedata.normalize("NFC", text).lower().translate(_DASHES)
    out = "".join(" " if ch.isspace() else ch for ch in out)
    out = "".join(ch for ch in out if ch in _ALLOWED)
    return " ".join(out.split())

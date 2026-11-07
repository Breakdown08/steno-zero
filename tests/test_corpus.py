"""Checks 28-33: corpus."""

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from steno_zero.corpus import extract_text, fetch_corpus, load_corpus, split_corpus
from tests.helpers import ROOT

HTML: str = (
    '<div class="ws-noexport"><p>шапка</p></div><div class="text"><style>x{}</style>'
    '<p>Раз<sup class="reference"><a>[1]</a></sup> два</p>'
    '<div class="references"><p>сноска</p></div><p>три<br>четыре &amp; пять</p></div><p>после</p>'
)
PAGES: dict[int, str] = {
    1: '<div class="text"><p>«Раз»</p></div>',
    2: '<div class="text"><p>Два!</p></div>',
}


def fake_get(oldid: int) -> str:
    return PAGES[oldid]


def write_sources(path: Path, sha: str | None) -> str:
    works: list[dict[str, Any]] = [
        {"author": "Чехов", "title": "А", "oldid": 1, "chars": 3},
        {"author": "Толстой", "title": "Б", "oldid": 2, "chars": 4},
    ]
    text: str = json.dumps(
        {"source": "https://ru.wikisource.org", "license": "PD-old-70", "corpus_sha256": sha, "works": works},
        ensure_ascii=False,
    )
    path.write_text(text, encoding="utf-8")
    return text


def test_extract_text() -> None:
    assert extract_text(HTML) == "Раз два\nтри четыре & пять"
    with pytest.raises(ValueError):
        extract_text("<div class='other'><p>x</p></div>")


def test_fetch_corpus_without_hash(tmp_path: Path) -> None:
    src: Path = tmp_path / "sources.json"
    before: str = write_sources(src, None)
    out: Path = tmp_path / "sub" / "classics.txt"
    sha: str = fetch_corpus(src, out, get=fake_get)
    assert out.read_bytes() == "раз два!\n".encode()
    assert sha == hashlib.sha256(out.read_bytes()).hexdigest()
    assert src.read_text(encoding="utf-8") == before


def test_fetch_corpus_hash_check(tmp_path: Path) -> None:
    src: Path = tmp_path / "sources.json"
    good: str = hashlib.sha256("раз два!\n".encode()).hexdigest()
    write_sources(src, good)
    out: Path = tmp_path / "classics.txt"
    assert fetch_corpus(src, out, get=fake_get) == good
    out.unlink()
    write_sources(src, "0" * 64)
    with pytest.raises(ValueError):
        fetch_corpus(src, out, get=fake_get)
    assert not out.exists()
    out.write_text("старое\n", encoding="utf-8")
    with pytest.raises(ValueError):
        fetch_corpus(src, out, get=fake_get)
    assert out.read_text(encoding="utf-8") == "старое\n"


def test_load_corpus(tmp_path: Path) -> None:
    p: Path = tmp_path / "c.txt"
    p.write_text("аб\n", encoding="utf-8")
    assert load_corpus(p) == "аб"
    assert load_corpus(p, hashlib.sha256(p.read_bytes()).hexdigest()) == "аб"
    with pytest.raises(ValueError):
        load_corpus(p, "0" * 64)
    p.write_text("аb\n", encoding="utf-8")  # latin b
    with pytest.raises(ValueError):
        load_corpus(p)


def test_split_corpus() -> None:
    assert split_corpus("абвгдежзик", 0.2) == ("абвгдежз", "ик")
    f: float
    for f in (0.0, 1.0):
        with pytest.raises(ValueError):
            split_corpus("абвгдежзик", f)


def test_committed_sources() -> None:
    data: dict[str, Any] = json.loads((ROOT / "data" / "corpus" / "sources.json").read_text(encoding="utf-8"))
    assert data["source"]
    assert data["license"] == "PD-old-70"
    sha: object = data["corpus_sha256"]
    assert isinstance(sha, str)
    assert len(sha) == 64
    assert set(sha) <= set("0123456789abcdef")
    works: list[dict[str, Any]] = data["works"]
    authors: set[str] = {w["author"] for w in works}
    assert {"Толстой", "Чехов"} <= authors
    w: dict[str, Any]
    for w in works:
        assert type(w["oldid"]) is int
        assert type(w["chars"]) is int
    total: int = sum(w["chars"] for w in works) + len(works) - 1
    assert 300_000 <= total <= 2_000_000

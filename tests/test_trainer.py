"""Checks 33, 35: help order, phrases, trainer data and data.js."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from steno_zero.alphabet import ALPHABET, normalize
from steno_zero.chords import FINGERS
from steno_zero.corpus import split_corpus
from steno_zero.simulate import segment
from steno_zero.table import Table
from steno_zero.trainer import (
    DATA_FORMAT,
    DATA_PREFIX,
    DATA_SUFFIX,
    VERSION,
    chord_label,
    data_js,
    help_order,
    pick_phrases,
    read_data_js,
    split_phrases,
    table_sha256,
    trainer_data,
    write_data_js,
)
from tests.helpers import GREEDY_EXTRA, base_table, costs, fragment, greedy_table

HOME: list[str] = ["вот одна фраза.", "вот другая фраза."]
EXAM: list[str] = ["второй экзамен тут.", "ещё один экзамен."]


def is_subsequence(small: list[str], big: list[str]) -> bool:
    it: Iterator[str] = iter(big)
    return all(x in it for x in small)


# 5-6: help_order


def test_help_order_base() -> None:
    assert help_order(base_table()) == [(ALPHABET[i], i + 1) for i in range(41)]


def test_help_order_greedy() -> None:
    order: list[tuple[str, int]] = help_order(greedy_table())
    assert order[:41] == [(ALPHABET[i], i + 1) for i in range(41)]
    assert order[41:] == [("аб", 72), ("ба", 96), ("бв", 64), ("б ", 68), ("аба", 136), ("абв ", 160)]
    assert set(order) == set(greedy_table().entries.items())
    assert len(order) == 41 + len(GREEDY_EXTRA)


# 7-13: phrases


@pytest.mark.parametrize(
    ("text", "min_len", "max_len", "limit", "expected"),
    [
        ("раз. два три! четыре пять? шесть", 1, 60, 10, ["два три!", "четыре пять?"]),
        ("а. - да! б. да! в.", 1, 60, 10, ["да!", "б."]),
        ("я. аа. ббб. вввв. ггггг. д", 3, 4, 10, ["аа.", "ббб."]),
        ("я. аб. ав. аг. ад. ае. аж. я", 1, 60, 3, ["аб.", "аг.", "ае."]),
        ("поезжай... дальше. вот так. я", 1, 60, 10, ["дальше.", "вот так."]),
    ],
)
def test_pick_phrases_examples(
    text: str, min_len: int, max_len: int, limit: int, expected: list[str]
) -> None:
    assert pick_phrases(text, min_len, max_len, limit) == expected


def test_pick_phrases_fragment() -> None:
    text: str = fragment()
    picked: list[str] = pick_phrases(text, 10, 60, 200)
    assert picked != []
    assert len(set(picked)) == len(picked)
    bad: list[str] = [
        p
        for p in picked
        if not 10 <= len(p) <= 60 or normalize(p) != p or p[-1] not in ".!?" or p[0] in " -" or p not in text
    ]
    assert bad == []


def test_pick_phrases_limit_is_uniform_subsequence() -> None:
    full: list[str] = pick_phrases(fragment(), 10, 60, 10_000)
    small: list[str] = pick_phrases(fragment(), 10, 60, 3)
    assert len(small) == 3
    assert is_subsequence(small, full)


@pytest.mark.parametrize(("min_len", "max_len", "limit"), [(0, 5, 1), (5, 4, 1), (1, 5, 0)])
def test_pick_phrases_bad_args(min_len: int, max_len: int, limit: int) -> None:
    with pytest.raises(ValueError):
        pick_phrases("а.", min_len, max_len, limit)


def test_split_phrases_fragment() -> None:
    home: list[str]
    exam: list[str]
    home, exam = split_phrases(fragment(), 10, 60, 200, 100)
    train: str
    test: str
    train, test = split_corpus(fragment(), 0.1)
    assert exam == pick_phrases(test, 10, 60, 100)
    assert home != []
    assert is_subsequence(home, pick_phrases(train, 10, 60, 200))
    assert set(home).isdisjoint(exam)


def test_split_phrases_removes_overlap() -> None:
    shared: str = "это общее предложение тут."
    tail: str = "ывок. " + shared + " конец текста."
    k: int = 1
    head: str = ""
    while True:
        head = "начало. " + shared + " ещё одна фраза для дома. " + "ж" * k + ". обр"
        if len(head) == int(0.9 * (len(head) + len(tail))):
            break
        k += 1
        assert k < 5000, "could not place the cut"
    text: str = head + tail
    train: str
    test: str
    train, test = split_corpus(text, 0.1)
    assert shared in pick_phrases(train, 10, 60, 200)
    assert shared in pick_phrases(test, 10, 60, 100)
    home: list[str]
    exam: list[str]
    home, exam = split_phrases(text, 10, 60, 200, 100)
    assert shared in exam
    assert shared not in home


def test_split_phrases_empty_sets() -> None:
    with pytest.raises(ValueError):
        split_phrases(fragment(), 70, 80, 200, 100)


# 14-16: trainer_data


def data_for(
    home: list[str] | None = None,
    exam: list[str] | None = None,
    size: int = 5,
    tables: list[tuple[str, Table]] | None = None,
) -> dict[str, Any]:
    return trainer_data(
        [("base", base_table())] if tables is None else tables,
        HOME if home is None else home,
        EXAM if exam is None else exam,
        size,
    )


def assert_tables_match(data: dict[str, Any], tables: dict[str, Table]) -> None:
    t: dict[str, Any]
    for t in data["tables"]:
        table: Table = tables[t["name"]]
        assert t["sha256"] == table_sha256(table)
        assert t["entries"] == [[p, c, chord_label(c)] for p, c in help_order(table)]
        assert all(
            label == " ".join(FINGERS[i] for i in range(10) if c >> i & 1) for _, c, label in t["entries"]
        )
        seg: list[list[list[Any]]]
        phr: list[str]
        for seg, phr in ((t["segments"], data["phrases"]), (t["exam_segments"], data["exam_phrases"])):
            assert len(seg) == len(phr)
            k: int
            for k in range(len(phr)):
                assert [c for _, c in seg[k]] == list(segment(phr[k], table, costs()).chords)
                assert "".join(p for p, _ in seg[k]) == phr[k]
                assert all(table.chord(p) == c for p, c in seg[k])


def test_trainer_data_header_and_tables() -> None:
    home: list[str]
    exam: list[str]
    home, exam = split_phrases(fragment(), 10, 60, 20, 100)
    data: dict[str, Any] = trainer_data([("base", base_table()), ("greedy", greedy_table())], home, exam, 5)
    assert data["format"] == DATA_FORMAT
    assert set(data) == {
        "format",
        "version",
        "fingers",
        "help_key",
        "exam_size",
        "phrases",
        "exam_phrases",
        "tables",
    }
    assert data["version"] == VERSION == 2
    assert data["fingers"] == list(FINGERS) == ["L4", "L3", "L2", "L1", "L0", "R0", "R1", "R2", "R3", "R4"]
    assert "keys" not in data
    assert data["help_key"] == "Slash"
    assert data["exam_size"] == 5
    assert data["phrases"] == home
    assert data["exam_phrases"] == exam
    assert [t["name"] for t in data["tables"]] == ["base", "greedy"]
    assert [t["sha256"] for t in data["tables"]] == [
        table_sha256(base_table()),
        table_sha256(greedy_table()),
    ]


def test_trainer_data_entries_and_segments() -> None:
    home: list[str]
    exam: list[str]
    home, exam = split_phrases(fragment(), 10, 60, 20, 100)
    data: dict[str, Any] = trainer_data([("base", base_table()), ("greedy", greedy_table())], home, exam, 5)
    assert_tables_match(data, {"base": base_table(), "greedy": greedy_table()})


def test_trainer_data_fewer_exam_phrases_than_size() -> None:
    data: dict[str, Any] = data_for(size=50)
    assert data["exam_size"] == 50


@pytest.mark.parametrize(
    "kwargs",
    [
        {"tables": []},
        {"tables": [("Evolved", base_table())]},
        {"tables": [("a b", base_table())]},
        {"tables": [("", base_table())]},
        {"tables": [("x", base_table()), ("x", base_table())]},
        {"home": []},
        {"exam": []},
        {"home": [""]},
        {"exam": [""]},
        {"home": ["Привет."]},
        {"home": ["вот так.", "вот так."]},
        {"exam": ["вот так.", "вот так."]},
        {"home": ["вот так.", "ещё тут."], "exam": ["вот так."]},
        {"size": 0},
    ],
    ids=lambda kw: json.dumps(list(kw), ensure_ascii=False),
)
def test_trainer_data_errors(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        data_for(**kwargs)


# 17-18: data.js


def test_data_js_text() -> None:
    d: dict[str, Any] = data_for()
    text: str = data_js(d)
    assert text.startswith(DATA_PREFIX)
    assert text.endswith(DATA_SUFFIX)
    middle: str = text[len(DATA_PREFIX) : len(text) - len(DATA_SUFFIX)]
    assert middle == json.dumps(d, ensure_ascii=False, separators=(",", ":"))


def test_write_and_read_data_js(tmp_path: Path) -> None:
    d: dict[str, Any] = data_for()
    out: Path = tmp_path / "sub" / "data.js"
    write_data_js(d, out)
    assert out.read_bytes() == data_js(d).encode("utf-8")
    assert read_data_js(out) == d


def good_middle() -> str:
    return json.dumps({"format": DATA_FORMAT, "version": 2, "phrases": []})


@pytest.mark.parametrize(
    "text",
    [
        good_middle() + DATA_SUFFIX,
        DATA_PREFIX + good_middle(),
        DATA_PREFIX + '{"format": ' + DATA_SUFFIX,
        DATA_PREFIX + json.dumps({"format": "other", "version": VERSION}) + DATA_SUFFIX,
        DATA_PREFIX + json.dumps({"format": DATA_FORMAT, "version": 3}) + DATA_SUFFIX,
    ],
    ids=["no-prefix", "no-suffix", "bad-json", "other-format", "version-3"],
)
def test_read_data_js_rejects(tmp_path: Path, text: str) -> None:
    path: Path = tmp_path / "data.js"
    path.write_text(text, encoding="utf-8", newline="\n")
    with pytest.raises(ValueError):
        read_data_js(path)


def test_read_data_js_accepts_minimal(tmp_path: Path) -> None:
    path: Path = tmp_path / "data.js"
    path.write_text(DATA_PREFIX + good_middle() + DATA_SUFFIX, encoding="utf-8", newline="\n")
    assert read_data_js(path)["version"] == 2


def test_read_data_js_version_1_is_no_longer_read(tmp_path: Path) -> None:
    path: Path = tmp_path / "data.js"
    text: str = DATA_PREFIX + json.dumps({"format": DATA_FORMAT, "version": 1, "phrases": []}) + DATA_SUFFIX
    path.write_text(text, encoding="utf-8", newline="\n")
    with pytest.raises(ValueError, match="version 1 is no longer read"):
        read_data_js(path)

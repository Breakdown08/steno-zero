"""Checks 9-20: features, metrics, data (no torch)."""

import hashlib
import json
import math
import random
import subprocess
from pathlib import Path
from typing import Any

import numpy
import pytest

from steno_zero.corpus import split_corpus
from steno_zero.evolve import EvolveParams, EvolveResult, evolve, random_table
from steno_zero.params import PenaltyParams
from steno_zero.simulate import Score, evaluate
from steno_zero.surrogate_data import (
    DATA_FORMAT,
    DATA_VERSION,
    FEATURES,
    N_FEATURES,
    SOURCES,
    DataParams,
    DataRow,
    PieceCounts,
    data_lines,
    generation_spearman,
    linear_baseline,
    metrics,
    read_data,
    spearman,
    split_by_seed,
    table_features,
)
from steno_zero.table import Table
from tests.helpers import BASE, base_table, costs, fragment
from tests.surrogate_helpers import (
    HEADER_KEYS,
    HORIZON,
    data_command,
    run_main,
    run_subprocess,
    small_rows,
    train_text,
)


def test_features_names() -> None:
    assert N_FEATURES == 16
    assert FEATURES == (
        *[f"k{i}" for i in range(10)],
        "keys",
        "cost",
        "length",
        "uses",
        "neighbours",
        "one",
    )
    assert DATA_FORMAT == "steno-zero/surrogate-data"
    assert DATA_VERSION == 1
    assert SOURCES == ("trajectory", "random")


def test_table_features_of_the_new_entry() -> None:
    table: Table = Table(BASE | {"аб": 72})
    feats: numpy.ndarray = table_features(table, PieceCounts("абаб аб"), costs(), 1e6)
    assert feats.shape == (42, 16)
    assert feats.dtype == numpy.float32
    chords: list[int] = list(table.entries.values())
    assert chords == sorted(chords)
    assert list(table.entries)[-1] == "аб"
    expected: list[float] = [0.0] * 16
    expected[3] = 1.0
    expected[6] = 1.0
    expected[10] = 0.2
    expected[11] = 0.23
    expected[12] = 0.25
    expected[13] = math.log1p(1e6 * 3 / 7) / math.log1p(1e6)
    expected[14] = 0.1
    expected[15] = 1.0
    numpy.testing.assert_allclose(feats[-1], expected, rtol=1e-6)


def test_table_features_first_row_is_lowest_chord() -> None:
    feats: numpy.ndarray = table_features(base_table(), PieceCounts("абаб аб"), costs(), 1e6)
    assert feats.shape == (41, 16)
    assert list(feats[0, :10]) == [1.0] + [0.0] * 9  # chord 1 -> bit 0
    assert feats[0, 10] == pytest.approx(0.1)
    assert numpy.all(feats[:, 15] == 1.0)


def test_piece_counts() -> None:
    counts: PieceCounts = PieceCounts("абаб аб")
    assert counts.count("аб") == 3
    assert counts.count("ба") == 1
    assert counts.count("аб") == 3  # cached, same answer
    assert counts.chars == 7
    with pytest.raises(ValueError):
        PieceCounts("")


def test_spearman() -> None:
    assert spearman([1, 2, 3], [10, 20, 30]) == pytest.approx(1.0)
    assert spearman([1, 2, 3], [3, 2, 1]) == pytest.approx(-1.0)
    assert spearman([1, 1, 2], [1, 2, 3]) == pytest.approx(0.8660254)
    assert spearman([5, 5, 5], [1, 2, 3]) is None
    assert spearman([1, 2, 3], [4, 4, 4]) is None
    with pytest.raises(ValueError):
        spearman([1], [1])
    with pytest.raises(ValueError):
        spearman([1, 2, 3], [1, 2])


def row(seed: int, source: str, generation: int | None, total: float) -> DataRow:
    return DataRow(seed, source, generation, total, base_table())


def test_generation_spearman_averages_valid_groups() -> None:
    rows: list[DataRow] = [
        row(1, "trajectory", 0, 1.0),
        row(1, "trajectory", 0, 2.0),
        row(1, "trajectory", 0, 3.0),
        row(1, "trajectory", 1, 1.0),
        row(1, "trajectory", 1, 2.0),
        row(1, "trajectory", 1, 3.0),
        row(1, "trajectory", 2, 1.0),  # only two rows: skipped
        row(1, "trajectory", 2, 2.0),
        row(2, "trajectory", 0, 7.0),  # constant total: skipped
        row(2, "trajectory", 0, 7.0),
        row(2, "trajectory", 0, 7.0),
        row(1, "random", None, 1.0),  # never grouped
        row(1, "random", None, 2.0),
        row(1, "random", None, 3.0),
    ]
    predicted: list[float] = [1, 2, 3, 3, 2, 1, 5, 6, 1, 2, 3, 9, 8, 7]
    assert generation_spearman(rows, predicted) == pytest.approx(0.0)


def test_generation_spearman_groups_by_seed_and_generation() -> None:
    rows: list[DataRow] = [row(s, "trajectory", 0, t) for s in (1, 2) for t in (1.0, 2.0, 3.0)]
    # one group of six would give a different answer than two perfect groups of three
    predicted: list[float] = [1, 2, 3, 1, 2, 3]
    assert generation_spearman(rows, predicted) == pytest.approx(1.0)


def test_generation_spearman_none_without_valid_groups() -> None:
    rows: list[DataRow] = [row(1, "trajectory", 0, 1.0), row(1, "trajectory", 0, 2.0)]
    assert generation_spearman(rows, [1.0, 2.0]) is None
    assert generation_spearman([], []) is None
    random_rows: list[DataRow] = [row(1, "random", None, t) for t in (1.0, 2.0, 3.0)]
    assert generation_spearman(random_rows, [1.0, 2.0, 3.0]) is None


def test_metrics() -> None:
    assert metrics([], []) == {"rows": 0, "spearman": None, "generation_spearman": None, "mae_s": None}
    rows: list[DataRow] = [row(1, "trajectory", 0, t) for t in (10.0, 20.0, 30.0)]
    result: dict[str, Any] = metrics(rows, [12.0, 18.0, 35.0])
    assert result["rows"] == 3
    assert result["mae_s"] == pytest.approx((2 + 2 + 5) / 3)
    assert result["spearman"] == pytest.approx(1.0)
    assert result["generation_spearman"] == pytest.approx(1.0)
    assert list(result) == ["rows", "spearman", "generation_spearman", "mae_s"]


def test_split_by_seed() -> None:
    rows: list[DataRow] = [row(s, "random", None, float(i)) for i, s in enumerate([5, 6, 7, 5, 6, 7, 7])]
    train: list[DataRow]
    holdout: list[DataRow]
    train, holdout = split_by_seed(rows, 1)
    assert {r.seed for r in holdout} == {7}
    assert len(holdout) == 3
    assert {r.seed for r in train} == {5, 6}
    assert len(train) + len(holdout) == len(rows)
    train, holdout = split_by_seed(rows, 2)
    assert {r.seed for r in holdout} == {6, 7}
    assert {r.seed for r in train} == {5}
    with pytest.raises(ValueError):
        split_by_seed(rows, 0)
    with pytest.raises(ValueError):
        split_by_seed(rows, 3)


def test_data_params_validation() -> None:
    with pytest.raises(ValueError):
        DataParams(seeds=1)
    with pytest.raises(ValueError):
        DataParams(generations=-1)
    with pytest.raises(ValueError):
        DataParams(random=-1)
    with pytest.raises(ValueError):
        DataParams(random_extra=-1)


def reference_trajectory(text: str, seed: int) -> tuple[int, list[Table], list[Score], list[int]]:
    fresh: list[Table] = []
    scores: list[Score] = []
    gens: list[int] = []

    def on_evaluated(g: int, tables: list[Table], sc: list[Score]) -> None:
        fresh.extend(tables)
        scores.extend(sc)
        gens.extend([g] * len(tables))

    res: EvolveResult = evolve(
        text,
        costs(),
        PenaltyParams(),
        HORIZON,
        EvolveParams(seed=seed, population=6, generations=3),
        on_evaluated=on_evaluated,
    )
    return res.history[-1].evaluations, fresh, scores, gens


def test_generate_data_content_and_order() -> None:
    text: str = train_text()
    rows: list[DataRow] = small_rows()
    pos: int = 0
    seed: int
    for seed in (1000, 1001):
        n: int
        fresh: list[Table]
        scores: list[Score]
        gens: list[int]
        n, fresh, scores, gens = reference_trajectory(text, seed)
        assert n > 0
        traj: list[DataRow] = rows[pos : pos + n]
        assert [r.table for r in traj] == fresh
        assert [r.generation for r in traj] == gens
        assert [r.total for r in traj] == [s.total for s in scores]
        assert all(r.seed == seed and r.source == "trajectory" for r in traj)
        rnd: list[DataRow] = rows[pos + n : pos + n + 5]
        gen: random.Random = random.Random(f"surrogate-random-{seed}")
        expected: list[Table] = [random_table(text, gen, 10, 6) for _ in range(5)]
        assert [r.table for r in rnd] == expected
        assert all(r.seed == seed and r.source == "random" and r.generation is None for r in rnd)
        pos += n + 5
    assert pos == len(rows)
    r: DataRow
    for r in rows:
        assert r.total == evaluate(text, r.table, costs(), PenaltyParams(), HORIZON).total


def test_generate_data_workers_do_not_matter() -> None:
    assert small_rows(workers=2) == small_rows(workers=1)


def test_generate_data_cli(tmp_path: Path) -> None:
    out: Path = tmp_path / "sub" / "d.jsonl"
    code: int
    stdout: str
    _: str
    code, stdout, _ = run_main(data_command(out))
    assert code == 0
    lines: list[str] = out.read_text(encoding="utf-8").split("\n")
    assert lines[-1] == ""
    body: list[str] = lines[:-1]
    ln: str
    for ln in body:
        assert ln == json.dumps(json.loads(ln), ensure_ascii=False)
    header: dict[str, Any] = json.loads(body[0])
    assert list(header) == HEADER_KEYS
    assert header["format"] == "steno-zero/surrogate-data"
    assert header["version"] == 1
    assert header["seed_base"] == 1000
    assert header["fit_sha256"] == hashlib.sha256(split_corpus(fragment(), 0.1)[0].encode()).hexdigest()
    assert header["text_sha256"] == hashlib.sha256(fragment().encode()).hexdigest()
    parsed: tuple[dict[str, Any], list[DataRow]] = read_data(out)
    assert parsed[1] == small_rows()
    table_rows: list[dict[str, Any]] = [json.loads(ln) for ln in body[1:]]
    assert len(table_rows) == len(parsed[1])
    assert list(table_rows[0]) == ["type", "seed", "source", "generation", "total", "entries"]
    assert table_rows[0]["type"] == "table"
    assert table_rows[0]["source"] == "trajectory"
    assert table_rows[0]["generation"] == 0
    info: dict[str, Any] = json.loads(stdout)
    assert stdout.count("\n") == 1
    assert list(info) == ["rows", "trajectory", "random", "seeds", "out"]
    assert info["rows"] == len(parsed[1])
    assert info["random"] == 10
    assert info["trajectory"] == info["rows"] - 10
    assert info["seeds"] == [1000, 1001]
    assert info["out"] == str(out)


def test_data_lines_roundtrip(tmp_path: Path) -> None:
    out: Path = tmp_path / "d.jsonl"
    assert run_main(data_command(out))[0] == 0
    header: dict[str, Any]
    rows: list[DataRow]
    header, rows = read_data(out)
    again: Path = tmp_path / "again.jsonl"
    again.write_text(data_lines(header, rows), encoding="utf-8", newline="\n")
    assert again.read_bytes() == out.read_bytes()


def test_data_bytes_do_not_depend_on_hashseed_or_workers(tmp_path: Path) -> None:
    files: list[bytes] = []
    hashseed: str
    workers: str
    for hashseed, workers in (("0", "1"), ("1", "1"), ("0", "2"), ("1", "2")):
        out: Path = tmp_path / f"d-{hashseed}-{workers}.jsonl"
        proc: subprocess.CompletedProcess[bytes] = run_subprocess(data_command(out, workers), hashseed)
        assert proc.returncode == 0, proc.stderr.decode()
        files.append(out.read_bytes())
    assert files[0] != b""
    assert all(f == files[0] for f in files)


def test_read_data_rejects_foreign_files(tmp_path: Path) -> None:
    out: Path = tmp_path / "d.jsonl"
    assert run_main(data_command(out))[0] == 0
    lines: list[str] = out.read_text(encoding="utf-8").split("\n")
    head: dict[str, Any] = json.loads(lines[0])
    key: str
    value: Any
    for key, value in (("format", "something/else"), ("version", 2)):
        bad: Path = tmp_path / f"bad-{key}.jsonl"
        bad.write_text(
            "\n".join([json.dumps({**head, key: value}, ensure_ascii=False), *lines[1:]]), encoding="utf-8"
        )
        with pytest.raises(ValueError):
            read_data(bad)


def test_linear_baseline_recovers_a_linear_target() -> None:
    text: str = train_text()
    counts: PieceCounts = PieceCounts(text)
    gen: random.Random = random.Random(5)
    tables: list[Table] = [random_table(text, gen, gen.randint(0, 40), 6) for _ in range(60)]
    rows: list[DataRow] = []
    t: Table
    i: int
    for i, t in enumerate(tables):
        f: numpy.ndarray = table_features(t, counts, costs(), HORIZON).sum(axis=0)
        total: float = 3000.0 * float(f[13]) + 40.0 * float(f[11]) + 7.0
        rows.append(DataRow(1000 if i < 45 else 1001, "random", None, total, t))
    train: list[DataRow]
    holdout: list[DataRow]
    train, holdout = split_by_seed(rows, 1)
    predicted: list[float] = linear_baseline(train, holdout, counts, costs(), HORIZON)
    assert len(predicted) == len(holdout)
    numpy.testing.assert_allclose(predicted, [r.total for r in holdout], rtol=1e-3)

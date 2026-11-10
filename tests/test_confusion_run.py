"""Confusion penalty, checks 16-18, 20-24: evolve, CLI, log."""

import json
from pathlib import Path
from typing import Any

import pytest

from steno_zero.evolve import EvolveParams, EvolveResult, GenerationRecord, evolve
from steno_zero.params import PenaltyParams
from steno_zero.plot import read_log
from tests.helpers import FRAGMENT_PATH, SUMMARY_KEYS, costs, fragment
from tests.test_evolve_cli import (
    args_for,
    gen_row,
    log_lines,
    run_main,
    run_row,
    subprocess_evolve,
    write_log,
)

HORIZON: float = 1_000_000.0
SUMMARY_ORDER: list[str] = ["chars", "chords", "entries", "t_char", "memory", "confusion", "total"]


def run(penalty: PenaltyParams, params: EvolveParams, workers: int = 1) -> EvolveResult:
    return evolve(fragment(), costs(), penalty, HORIZON, params, workers=workers)


def test_evolve_switched_off() -> None:
    res: EvolveResult = run(
        PenaltyParams(confusion_s=0.0), EvolveParams(seed=0, population=8, generations=10)
    )
    assert res.score.confusion == 0.0
    default: EvolveResult = run(PenaltyParams(), EvolveParams(seed=0, population=8, generations=10))
    assert default.score.confusion > 0.0
    assert len(res.history) == 11
    r: GenerationRecord
    for r in res.history:
        assert r.confusion == 0.0
        assert r.best_total == HORIZON * r.t_char + r.memory


def test_penalty_changes_the_path() -> None:
    params: EvolveParams = EvolveParams(seed=0, population=16, generations=30)
    on: EvolveResult = run(PenaltyParams(), params)
    off: EvolveResult = run(PenaltyParams(confusion_s=0.0), params)
    assert on.history != off.history
    assert on.score.confusion > 0.0


def test_workers_with_penalty() -> None:
    params: EvolveParams = EvolveParams(seed=0, population=8, generations=5)
    penalty: PenaltyParams = PenaltyParams(confusion_s=5.0)
    one: EvolveResult = run(penalty, params, workers=1)
    two: EvolveResult = run(penalty, params, workers=2)
    assert one.history == two.history
    assert one.best == two.best
    assert one.score.confusion > 0.0


def test_log_penalty_keys_and_flag(tmp_path: Path) -> None:
    code: int
    _: str
    code, _, _ = run_main(args_for(tmp_path / "off", "--confusion-s", "0"))
    assert code == 0
    rows: list[dict[str, Any]] = log_lines(tmp_path / "off")
    assert rows[0]["version"] == 3
    assert rows[0]["penalty_params"]["confusion_s"] == 0.0
    assert list(rows[0]["penalty_params"]) == [
        "entry_s",
        "rarity_s",
        "rarity_uses",
        "slip_prob",
        "confusion_s",
    ]
    gens: list[dict[str, Any]] = rows[1:-1]
    assert len(gens) == 6
    g: dict[str, Any]
    for g in gens:
        assert g["confusion"] == 0.0
    code, _, _ = run_main(args_for(tmp_path / "on"))
    assert code == 0
    assert (tmp_path / "on" / "log.jsonl").read_bytes() != (tmp_path / "off" / "log.jsonl").read_bytes()
    assert log_lines(tmp_path / "on")[-2]["confusion"] > 0.0


def test_log_totals_include_confusion(tmp_path: Path) -> None:
    code: int
    _: str
    code, _, _ = run_main(args_for(tmp_path / "r"))
    assert code == 0
    result: dict[str, Any] = log_lines(tmp_path / "r")[-1]
    ev: dict[str, Any] = summary(
        ["evaluate", "--table", str(tmp_path / "r" / "best.json"), "--corpus", str(FRAGMENT_PATH),
         "--part", "train"]
    )  # fmt: skip
    assert ev["confusion"] > 0.0
    assert ev["total"] == result["train_total"]


def test_byte_reproducibility_with_penalty(tmp_path: Path) -> None:
    a: Path = tmp_path / "a"
    b: Path = tmp_path / "b"
    subprocess_evolve(a, "0", "1")
    subprocess_evolve(b, "1", "2")
    name: str
    for name in ("log.jsonl", "best.json"):
        assert (a / name).read_bytes() == (b / name).read_bytes()
    gen: dict[str, Any] = log_lines(a)[-2]
    assert gen["confusion"] > 0.0


def summary(argv: list[str]) -> dict[str, Any]:
    code: int
    out: str
    _: str
    code, out, _ = run_main(argv)
    assert code == 0
    data: dict[str, Any] = json.loads(out.strip().splitlines()[-1])
    return data


def test_summary_rival_and_evaluate(tmp_path: Path) -> None:
    table: Path = tmp_path / "r.json"
    base: list[str] = ["--corpus", str(FRAGMENT_PATH)]
    cmds: dict[str, list[str]] = {
        "rival": ["rival", *base, "--out", str(table)],
        "evaluate": ["evaluate", *base, "--table", str(table)],
    }
    summary(cmds["rival"])
    name: str
    for name in cmds:
        on: dict[str, Any] = summary(cmds[name])
        off: dict[str, Any] = summary([*cmds[name], "--confusion-s", "0"])
        assert list(on) == SUMMARY_ORDER
        assert set(on) == SUMMARY_KEYS
        assert on["confusion"] > 0.0
        assert on["total"] == pytest.approx(1_000_000.0 * on["t_char"] + on["memory"] + on["confusion"])
        assert list(off) == SUMMARY_ORDER
        assert off["confusion"] == 0.0
        assert off["total"] == pytest.approx(1_000_000.0 * off["t_char"] + off["memory"])
        assert off["memory"] == on["memory"]
        assert off["t_char"] == on["t_char"]
        assert off["chords"] == on["chords"]


def test_negative_confusion_s(tmp_path: Path) -> None:
    table: Path = tmp_path / "r.json"
    assert summary(["rival", "--corpus", str(FRAGMENT_PATH), "--out", str(table)])["entries"] == 41
    cmds: list[list[str]] = [
        ["rival", "--corpus", str(FRAGMENT_PATH)],
        ["evaluate", "--corpus", str(FRAGMENT_PATH), "--table", str(table)],
        args_for(tmp_path / "e"),
    ]
    cmd: list[str]
    for cmd in cmds:
        code: int
        err: str
        _: str
        code, _, err = run_main([*cmd, "--confusion-s", "-1"])
        assert code == 1, cmd
        assert err.strip() != ""
        exc: pytest.ExceptionInfo[SystemExit]
        with pytest.raises(SystemExit) as exc:
            run_main([*cmd, "--confusion-s", "abc"])
        assert exc.value.code == 2


def test_read_log_versions(tmp_path: Path) -> None:
    rows: list[dict[str, Any]] = [gen_row(0, 100.0, True), gen_row(1, 95.0, True)]
    v: int
    for v in (1, 2, 3, 4):
        log: Path = tmp_path / f"v{v}.jsonl"
        write_log(log, [run_row() | {"version": v}, *rows])
        run_: dict[str, Any]
        gens: list[dict[str, Any]]
        run_, gens = read_log(log)
        assert run_["version"] == v
        assert len(gens) == 2
    bad: Path = tmp_path / "v5.jsonl"
    write_log(bad, [run_row() | {"version": 5}, *rows])
    with pytest.raises(ValueError):
        read_log(bad)
    code: int
    err: str
    _: str
    code, _, err = run_main(["plot", "--log", str(bad)])
    assert code == 1
    assert err.strip() != ""

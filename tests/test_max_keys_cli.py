"""Key limit, checks 18-19, 20, 23-28: the --max-keys flag, neutrality at 10, the log."""

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from steno_zero.table import Table
from tests.helpers import BASE, FRAGMENT_PATH, SUMMARY_KEYS, base_table
from tests.test_evolve_cli import RUN_KEYS, args_for, log_lines, run_main
from tests.test_trainer_cli import export_args, make_tables

NEUTRAL_SHA256: str = "f8fc785448c1aae4903ba15f7f21ed5dba48d1d6c517fbf07b549ccceed4ba40"
WIDE: dict[str, int] = BASE | {"аа": 1023}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_table(path: Path, table: Table) -> Path:
    path.write_text(table.to_json(), encoding="utf-8")
    return path


def summary_of(argv: list[str]) -> dict[str, Any]:
    code: int
    out: str
    _: str
    code, out, _ = run_main(argv)
    assert code == 0
    data: dict[str, Any] = json.loads(out.strip().splitlines()[-1])
    return data


# 18-19: neutrality


def test_max_keys_10_is_the_old_path(tmp_path: Path) -> None:
    code: int
    _: str
    code, _, _ = run_main(args_for(tmp_path / "k10", "--max-keys", "10"))
    assert code == 0
    assert sha(tmp_path / "k10" / "best.json") == NEUTRAL_SHA256


def test_default_limit_changes_the_path(tmp_path: Path) -> None:
    code: int
    _: str
    code, _, _ = run_main(args_for(tmp_path / "k6"))
    assert code == 0
    best: Path = tmp_path / "k6" / "best.json"
    assert sha(best) != NEUTRAL_SHA256
    assert Table.from_json(best.read_text(encoding="utf-8")).over_keys(6) == []


# 20: log


def test_log_records_max_keys(tmp_path: Path) -> None:
    code: int
    _: str
    code, _, _ = run_main(args_for(tmp_path / "d"))
    assert code == 0
    run: dict[str, Any] = log_lines(tmp_path / "d")[0]
    assert list(run) == RUN_KEYS
    assert run["version"] == 3
    assert run["max_keys"] == 6
    code, _, _ = run_main(args_for(tmp_path / "four", "--max-keys", "4"))
    assert code == 0
    run = log_lines(tmp_path / "four")[0]
    assert list(run) == RUN_KEYS
    assert run["version"] == 3
    assert run["max_keys"] == 4
    best: Table = Table.from_json((tmp_path / "four" / "best.json").read_text(encoding="utf-8"))
    assert best.over_keys(4) == []


# 23: rival


def test_rival_flag(tmp_path: Path) -> None:
    out: Path = tmp_path / "r.json"
    base: list[str] = ["rival", "--corpus", str(FRAGMENT_PATH)]
    summary_of([*base, "--max-keys", "2", "--out", str(out)])
    assert Table.from_json(out.read_text(encoding="utf-8")).over_keys(2) == []
    assert summary_of(base) == summary_of([*base, "--max-keys", "10"])


# 24-25: evaluate


def test_evaluate_refuses_wide_table(tmp_path: Path) -> None:
    table: Path = write_table(tmp_path / "wide.json", Table(WIDE))
    argv: list[str] = ["evaluate", "--corpus", str(FRAGMENT_PATH), "--table", str(table)]
    code: int
    out: str
    err: str
    code, out, err = run_main(argv)
    assert code == 1
    assert out == ""
    assert "--max-keys" in err
    assert "'аа'" in err
    ok: dict[str, Any] = summary_of([*argv, "--max-keys", "10"])
    assert set(ok) == SUMMARY_KEYS


def test_evaluate_base_table_limits(tmp_path: Path) -> None:
    table: Path = write_table(tmp_path / "base.json", base_table())
    argv: list[str] = ["evaluate", "--corpus", str(FRAGMENT_PATH), "--table", str(table)]
    assert summary_of(argv) == summary_of([*argv, "--max-keys", "5"])
    code: int
    out: str
    err: str
    code, out, err = run_main([*argv, "--max-keys", "4"])
    assert code == 1
    assert out == ""
    assert "'э'" in err
    assert "--max-keys" in err


# 26: trainer export


def test_export_refuses_wide_table(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rival: Path
    base: Path
    rival, base = make_tables(tmp_path, capsys)
    wide: Path = write_table(tmp_path / "wide.json", Table(WIDE))
    out: Path = tmp_path / "d.js"
    argv: list[str] = [*export_args(rival, base, out), "--table", f"wide={wide}"]
    code: int
    stdout: str
    err: str
    code, stdout, err = run_main(argv)
    assert code == 1
    assert "wide" in err
    assert "--max-keys" in err
    assert not out.exists()
    out.write_bytes(b"old bytes")
    code, stdout, err = run_main(argv)
    assert code == 1
    assert out.read_bytes() == b"old bytes"
    out.unlink()
    code, stdout, err = run_main([*argv, "--max-keys", "10"])
    assert code == 0
    assert out.exists()


def test_export_checks_tables_before_reading_corpus(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rival: Path
    base: Path
    rival, base = make_tables(tmp_path, capsys)
    wide: Path = write_table(tmp_path / "wide.json", Table(WIDE))
    out: Path = tmp_path / "d.js"
    argv: list[str] = [
        "trainer", "export", "--table", f"rival={rival}", "--table", f"wide={wide}",
        "--corpus", str(tmp_path / "missing.txt"), "--out", str(out),
    ]  # fmt: skip
    code: int
    _: str
    err: str
    code, _, err = run_main(argv)
    assert code == 1
    assert "wide" in err
    assert not out.exists()


# 28: range of the flag


def commands(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> dict[str, list[str]]:
    rival: Path
    base: Path
    rival, base = make_tables(tmp_path, capsys)
    return {
        "rival": ["rival", "--corpus", str(FRAGMENT_PATH)],
        "evaluate": ["evaluate", "--corpus", str(FRAGMENT_PATH), "--table", str(base)],
        "evolve": args_for(tmp_path / "ev"),
        "export": export_args(rival, base, tmp_path / "d.js"),
    }


@pytest.mark.parametrize("name", ["rival", "evaluate", "evolve", "export"])
@pytest.mark.parametrize("bad", ["1", "11", "0", "-3"])
def test_flag_out_of_range(tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str, bad: str) -> None:
    argv: list[str] = commands(tmp_path, capsys)[name]
    code: int
    out: str
    err: str
    code, out, err = run_main([*argv, "--max-keys", bad])
    assert code == 1
    assert err.strip() != ""


@pytest.mark.parametrize("name", ["rival", "evaluate", "evolve", "export"])
def test_flag_not_a_number(tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str) -> None:
    argv: list[str] = commands(tmp_path, capsys)[name]
    assert run_main([*argv, "--max-keys", "6"])[0] == 0  # the flag exists; only the value is wrong below
    exc: pytest.ExceptionInfo[SystemExit]
    with pytest.raises(SystemExit) as exc:
        run_main([*argv, "--max-keys", "x"])
    assert exc.value.code == 2

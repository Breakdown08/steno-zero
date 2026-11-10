"""Checks 28-31, 35: CLI with a trained model (torch needed: skipped without it, CI has it)."""

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("torch")


from steno_zero.plot import plot_log, read_log  # noqa: E402
from steno_zero.surrogate import Surrogate, load_surrogate  # noqa: E402
from tests.helpers import FRAGMENT_PATH  # noqa: E402
from tests.surrogate_helpers import data_command, run_main, train_text  # noqa: E402
from tests.test_evolve_cli import GEN_KEYS, PNG, RESULT_KEYS, RUN_KEYS  # noqa: E402

META_KEYS: list[str] = [
    "fit_sha256", "fit_chars", "sample_chars", "sample_chunks", "text_sha256", "horizon", "max_keys",
    "cost_params", "penalty_params", "features", "hidden", "y_mean", "y_std", "train_params",
    "seeds_train", "seeds_holdout", "torch_version",
]  # fmt: skip
TRAIN_STDOUT_KEYS: list[str] = [
    "rows_train", "rows_holdout", "spearman", "generation_spearman", "linear_generation_spearman",
    "train_s", "out",
]  # fmt: skip
REPORT_KEYS: list[str] = [
    "format", "version", "model_sha256", "train_params", "seeds_train", "seeds_holdout", "rows_train",
    "rows_holdout", "train_s", "torch_version", "epochs", "holdout", "linear",
]  # fmt: skip


@pytest.fixture(scope="module")
def trained(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, str]:
    root: Path = tmp_path_factory.mktemp("model")
    data: Path = root / "d.jsonl"
    assert run_main(data_command(data))[0] == 0
    model: Path = root / "model.pt"
    code: int
    stdout: str
    err: str
    code, stdout, err = run_main(
        ["surrogate", "train", "--data", str(data), "--corpus", str(FRAGMENT_PATH), "--epochs", "2",
         "--hidden", "8", "--out", str(model)]
    )  # fmt: skip
    assert code == 0, err
    return model, stdout


def test_train_command(trained: tuple[Path, str]) -> None:
    model: Path
    stdout: str
    model, stdout = trained
    assert model.is_file()
    report_path: Path = model.with_suffix(".json")
    assert report_path.is_file()
    raw: str = report_path.read_text(encoding="utf-8")
    assert raw.endswith("}\n")
    report: dict[str, Any] = json.loads(raw)
    assert raw == json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    assert list(report) == REPORT_KEYS
    assert report["model_sha256"] == hashlib.sha256(model.read_bytes()).hexdigest()
    assert stdout.count("\n") == 1
    info: dict[str, Any] = json.loads(stdout)
    assert list(info) == TRAIN_STDOUT_KEYS
    assert info["out"] == str(model)
    assert info["spearman"] == report["holdout"]["all"]["spearman"]
    assert info["generation_spearman"] == report["holdout"]["all"]["generation_spearman"]
    assert info["linear_generation_spearman"] == report["linear"]["all"]["generation_spearman"]
    assert info["rows_train"] == report["rows_train"]
    assert info["train_s"] == report["train_s"]
    loaded: Surrogate = load_surrogate(model, train_text())
    assert set(loaded.meta) == set(META_KEYS)
    with pytest.raises(ValueError):
        load_surrogate(model, train_text() + " ")


def evolve_args(out: Path, model: Path, workers: str = "1", *extra: str) -> list[str]:
    return [
        "evolve", "--corpus", str(FRAGMENT_PATH), "--population", "8", "--generations", "3",
        "--workers", workers, "--surrogate", str(model), "--oversample", "3", "--out", str(out), *extra,
    ]  # fmt: skip


def test_evolve_with_surrogate_log(trained: tuple[Path, str], tmp_path: Path) -> None:
    model: Path = trained[0]
    out: Path = tmp_path / "r"
    code: int
    _: str
    err: str
    code, _, err = run_main(evolve_args(out, model))
    assert code == 0, err
    rows: list[dict[str, Any]] = [
        json.loads(ln) for ln in (out / "log.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    run: dict[str, Any] = rows[0]
    assert run["version"] == 4
    assert list(run) == [*RUN_KEYS, "surrogate_sha256", "oversample"]
    assert run["oversample"] == 3
    assert run["surrogate_sha256"] == hashlib.sha256(model.read_bytes()).hexdigest()
    gens: list[dict[str, Any]] = rows[1:-1]
    assert len(gens) == 4
    assert all(list(g) == GEN_KEYS for g in gens)
    assert list(rows[-1]) == RESULT_KEYS
    assert read_log(out / "log.jsonl")[0]["version"] == 4
    png: Path = tmp_path / "r.png"
    plot_log(out / "log.jsonl", png)
    assert png.read_bytes().startswith(PNG)
    ecode: int
    eout: str
    ecode, eout, _ = run_main(
        ["evaluate", "--table", str(out / "best.json"), "--corpus", str(FRAGMENT_PATH), "--part", "train"]
    )
    assert ecode == 0
    assert json.loads(eout.strip().splitlines()[-1])["total"] == rows[-1]["train_total"]


def test_evolve_with_surrogate_is_reproducible(trained: tuple[Path, str], tmp_path: Path) -> None:
    model: Path = trained[0]
    outs: list[Path] = [tmp_path / n for n in ("a", "b", "c")]
    assert run_main(evolve_args(outs[0], model, "1"))[0] == 0
    assert run_main(evolve_args(outs[1], model, "2"))[0] == 0
    assert run_main(evolve_args(outs[2], model, "1"))[0] == 0
    name: str
    for name in ("log.jsonl", "best.json"):
        data: bytes = (outs[0] / name).read_bytes()
        assert data != b""
        assert (outs[1] / name).read_bytes() == data
        assert (outs[2] / name).read_bytes() == data


def test_evolve_surrogate_option_errors(trained: tuple[Path, str], tmp_path: Path) -> None:
    model: Path = trained[0]
    base: list[str] = ["evolve", "--corpus", str(FRAGMENT_PATH), "--population", "8", "--generations", "2",
                       "--workers", "1", "--out", str(tmp_path / "x")]  # fmt: skip
    code: int
    _: str
    err: str
    code, _, err = run_main([*base, "--oversample", "3"])
    assert code == 1
    assert "--oversample needs --surrogate" in err
    code, _, err = run_main([*base, "--surrogate", str(model), "--oversample", "0"])
    assert code == 1
    assert err.startswith("error:")
    flag: list[str]
    for flag in (["--horizon", "500000"], ["--max-keys", "10"], ["--confusion-s", "0"]):
        code, _, err = run_main([*base, "--surrogate", str(model), *flag])
        assert code == 1, flag
        assert "surrogate model was trained for" in err, flag


def test_compare_command(trained: tuple[Path, str], tmp_path: Path) -> None:
    model: Path = trained[0]
    out: Path = tmp_path / "c.json"
    code: int
    stdout: str
    err: str
    code, stdout, err = run_main(
        ["surrogate", "compare", "--model", str(model), "--corpus", str(FRAGMENT_PATH), "--seeds", "2",
         "--population", "8", "--generations", "3", "--oversample", "3", "--workers", "1",
         "--out", str(out)]
    )  # fmt: skip
    assert code == 0, err
    raw: str = out.read_text(encoding="utf-8")
    report: dict[str, Any] = json.loads(raw)
    assert raw == json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    assert list(report) == ["format", "version", "model", "params", "runs", "summary"]
    assert report["format"] == "steno-zero/surrogate-compare"
    meta: dict[str, Any] = load_surrogate(model, train_text()).meta
    assert report["params"]["horizon"] == meta["horizon"]
    assert report["params"]["max_keys"] == meta["max_keys"]
    assert report["params"]["sample_chars"] == meta["sample_chars"]
    assert report["params"]["fit_sha256"] == meta["fit_sha256"]
    assert report["params"]["seeds"] == [0, 1]
    assert report["params"]["oversample"] == 3
    assert report["model"]["sha256"] == hashlib.sha256(model.read_bytes()).hexdigest()
    assert len(report["runs"]) == 4
    keys: list[str] = [
        "seed", "mode", "final_total", "exact_evaluations", "screened", "wall_s", "target",
        "generation_to_target", "evaluations_to_target", "seconds_to_target",
    ]  # fmt: skip
    assert all(list(r) == keys for r in report["runs"])
    assert stdout.count("\n") == 1
    assert json.loads(stdout) == report["summary"]

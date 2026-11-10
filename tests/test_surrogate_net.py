"""Checks 21-24: the network and training (torch needed: skipped without it, CI has it)."""

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("torch")

import torch  # noqa: E402

from steno_zero.surrogate import Surrogate, SurrogateNet, TrainParams, train_surrogate  # noqa: E402
from steno_zero.surrogate_data import DataRow  # noqa: E402
from steno_zero.table import Table  # noqa: E402
from tests.surrogate_helpers import cli_data, train_text  # noqa: E402

REPORT_ORDER: list[str] = [
    "format", "version", "model_sha256", "train_params", "seeds_train", "seeds_holdout", "rows_train",
    "rows_holdout", "train_s", "torch_version", "epochs", "holdout", "linear",
]  # fmt: skip
METRIC_KEYS: list[str] = ["rows", "spearman", "generation_spearman", "mae_s"]


def test_net_shape_permutation_and_padding() -> None:
    torch.manual_seed(0)
    net: SurrogateNet = SurrogateNet(16, 8)
    net.eval()
    x: torch.Tensor = torch.randn(3, 5, 16)
    mask: torch.Tensor = torch.ones(3, 5, dtype=torch.bool)
    mask[1, 3:] = False
    with torch.no_grad():
        out: torch.Tensor = net(x, mask)
        assert out.shape == (3,)
        assert out.dtype == torch.float32
        perm: torch.Tensor = torch.tensor([4, 2, 0, 3, 1])
        permuted: torch.Tensor = net(x[:, perm], mask[:, perm])
        assert torch.allclose(out, permuted, atol=1e-5)
        padded_x: torch.Tensor = torch.cat([x, torch.randn(3, 4, 16) * 100.0], dim=1)
        padded_mask: torch.Tensor = torch.cat([mask, torch.zeros(3, 4, dtype=torch.bool)], dim=1)
        padded: torch.Tensor = net(padded_x, padded_mask)
        assert torch.allclose(out, padded, atol=1e-5)
    assert not torch.equal(out, torch.zeros(3))


@pytest.fixture(scope="module")
def small(tmp_path_factory: pytest.TempPathFactory) -> tuple[dict[str, Any], list[DataRow]]:
    return cli_data(tmp_path_factory.mktemp("d") / "d.jsonl")


def test_training_is_deterministic(small: tuple[dict[str, Any], list[DataRow]]) -> None:
    header: dict[str, Any]
    rows: list[DataRow]
    header, rows = small
    params: TrainParams = TrainParams(seed=0, epochs=2, hidden=8)
    a: Surrogate
    b: Surrogate
    c: Surrogate
    a = train_surrogate(header, rows, train_text(), params)[0]
    b = train_surrogate(header, rows, train_text(), params)[0]
    c = train_surrogate(header, rows, train_text(), TrainParams(seed=1, epochs=2, hidden=8))[0]
    sa: dict[str, torch.Tensor] = a.net.state_dict()
    sb: dict[str, torch.Tensor] = b.net.state_dict()
    sc: dict[str, torch.Tensor] = c.net.state_dict()
    assert list(sa) == list(sb)
    name: str
    for name in sa:
        assert torch.equal(sa[name], sb[name]), name
    assert any(not torch.equal(sa[name], sc[name]) for name in sa)
    tables: list[Table] = [r.table for r in rows[:10]]
    assert a.predict(tables) == b.predict(tables)
    assert len(a.predict(tables)) == 10
    assert a.predict([]) == []


def test_train_rejects_other_text(small: tuple[dict[str, Any], list[DataRow]]) -> None:
    header: dict[str, Any]
    rows: list[DataRow]
    header, rows = small
    with pytest.raises(ValueError):
        train_surrogate(header, rows, train_text() + " ", TrainParams(epochs=1, hidden=8))


def test_report_structure(small: tuple[dict[str, Any], list[DataRow]]) -> None:
    header: dict[str, Any]
    rows: list[DataRow]
    header, rows = small
    report: dict[str, Any]
    report = train_surrogate(header, rows, train_text(), TrainParams(seed=0, epochs=3, hidden=8))[1]
    # model_sha256 is written by the CLI after saving, so the library report may or may not hold it
    keys: list[str] = [k for k in report if k != "model_sha256"]
    assert keys == [k for k in REPORT_ORDER if k != "model_sha256"]
    assert report["format"] == "steno-zero/surrogate-report"
    assert len(report["epochs"]) == 3
    assert [e["epoch"] for e in report["epochs"]] == [1, 2, 3]
    assert report["seeds_train"] == [1000]
    assert report["seeds_holdout"] == [1001]
    assert report["rows_train"] + report["rows_holdout"] == len(rows)
    group: str
    part: str
    for group in ("holdout", "linear"):
        assert list(report[group]) == ["all", "trajectory", "random"]
        for part in ("all", "trajectory", "random"):
            assert list(report[group][part]) == METRIC_KEYS
    assert report["holdout"]["all"]["rows"] == report["rows_holdout"]
    assert report["holdout"]["random"]["rows"] == 5


def test_quality_on_the_fragment(tmp_path: Path) -> None:
    header: dict[str, Any]
    rows: list[DataRow]
    header, rows = cli_data(
        tmp_path / "q.jsonl",
        "--seeds", "2", "--population", "8", "--generations", "10", "--random", "150",
        "--random-extra", "60",
    )  # fmt: skip
    report: dict[str, Any]
    report = train_surrogate(
        header, rows, train_text(), TrainParams(seed=0, epochs=60, hidden=32, holdout=1)
    )[1]
    rho: float | None = report["holdout"]["random"]["spearman"]
    assert rho is not None
    assert rho >= 0.5

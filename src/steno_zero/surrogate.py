"""Surrogate network (torch): a DeepSets model of the table, training, saving, loading."""

import dataclasses
import hashlib
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy
import torch

from steno_zero.chords import chord_costs
from steno_zero.params import CostParams
from steno_zero.surrogate_data import (
    FEATURES,
    N_FEATURES,
    DataRow,
    PieceCounts,
    linear_baseline,
    metrics,
    split_by_seed,
    table_features,
)
from steno_zero.table import Table

MODEL_FORMAT: str = "steno-zero/surrogate-model"
MODEL_VERSION: int = 1
REPORT_FORMAT: str = "steno-zero/surrogate-report"
SUM_SCALE: float = 100.0  # the masked sum is divided by this, so that it stays near 1 for ~100 entries
PREDICT_CHUNK: int = 512


@dataclass(frozen=True)
class TrainParams:
    seed: int = 0
    epochs: int = 30
    batch: int = 256
    lr: float = 1e-3
    hidden: int = 64
    holdout: int = 1

    def __post_init__(self) -> None:
        if self.epochs < 1:
            raise ValueError("epochs must be at least 1")
        if self.batch < 1:
            raise ValueError("batch must be at least 1")
        if not self.lr > 0:
            raise ValueError("lr must be positive")
        if self.hidden < 1:
            raise ValueError("hidden must be at least 1")
        if self.holdout < 1:
            raise ValueError("holdout must be at least 1")


class SurrogateNet(torch.nn.Module):
    def __init__(self, n_features: int, hidden: int) -> None:
        super().__init__()
        self.phi: torch.nn.Sequential = torch.nn.Sequential(
            torch.nn.Linear(n_features, hidden),
            torch.nn.ReLU(),
            torch.nn.Linear(hidden, hidden),
            torch.nn.ReLU(),
        )
        self.rho: torch.nn.Sequential = torch.nn.Sequential(
            torch.nn.Linear(hidden, hidden),
            torch.nn.ReLU(),
            torch.nn.Linear(hidden, 1),
        )

    def forward(self, x: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
        per_entry: torch.Tensor = self.phi(x) * mask.unsqueeze(-1).to(x.dtype)
        pooled: torch.Tensor = per_entry.sum(dim=1) / SUM_SCALE
        out: torch.Tensor = self.rho(pooled).squeeze(-1)
        return out


def _pad(items: Sequence[torch.Tensor]) -> tuple[torch.Tensor, torch.Tensor]:
    x: torch.Tensor = torch.nn.utils.rnn.pad_sequence(list(items), batch_first=True)
    lengths: torch.Tensor = torch.tensor([len(t) for t in items])
    mask: torch.Tensor = torch.arange(x.shape[1]).unsqueeze(0) < lengths.unsqueeze(1)
    return x, mask


class Surrogate:
    def __init__(self, net: SurrogateNet, meta: dict[str, Any], text: str) -> None:
        self.net: SurrogateNet = net
        self.meta: dict[str, Any] = meta
        self._counts: PieceCounts = PieceCounts(text)
        self._costs: tuple[int, ...] = chord_costs(_cost_params(meta["cost_params"]))

    def features(self, table: Table) -> torch.Tensor:
        return torch.from_numpy(table_features(table, self._counts, self._costs, self.meta["horizon"]))

    def _predict_features(self, items: Sequence[torch.Tensor]) -> list[float]:
        if not items:
            return []
        self.net.eval()
        x: torch.Tensor
        mask: torch.Tensor
        x, mask = _pad(items)
        with torch.no_grad():
            y: torch.Tensor = self.net(x, mask)
        out: numpy.ndarray = y.double().numpy() * self.meta["y_std"] + self.meta["y_mean"]
        return [float(v) for v in out]

    def predict(self, tables: Sequence[Table]) -> list[float]:
        return self._predict_features([self.features(t) for t in tables])

    def predict_chunked(self, tables: Sequence[Table]) -> list[float]:
        out: list[float] = []
        i: int
        for i in range(0, len(tables), PREDICT_CHUNK):
            out.extend(self.predict(tables[i : i + PREDICT_CHUNK]))
        return out


def _cost_params(data: dict[str, Any]) -> CostParams:
    return CostParams(
        base_ms=data["base_ms"], extra_key_ms=data["extra_key_ms"], finger_ms=tuple(data["finger_ms"])
    )


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def train_surrogate(
    header: dict[str, Any], rows: Sequence[DataRow], text: str, params: TrainParams
) -> tuple[Surrogate, dict[str, Any]]:
    if _sha(text) != header["fit_sha256"]:
        raise ValueError("the text is not the fitness sample the data was made on")
    train: list[DataRow]
    holdout: list[DataRow]
    train, holdout = split_by_seed(rows, params.holdout)
    started: float = time.monotonic()
    cost_params: CostParams = _cost_params(header["cost_params"])
    costs: tuple[int, ...] = chord_costs(cost_params)
    horizon: float = header["horizon"]
    counts: PieceCounts = PieceCounts(text)
    totals: numpy.ndarray = numpy.asarray([r.total for r in train], dtype=numpy.float64)
    y_mean: float = float(totals.mean())
    y_std: float = float(totals.std()) or 1.0
    xs: list[torch.Tensor] = [
        torch.from_numpy(table_features(r.table, counts, costs, horizon)) for r in train
    ]
    ys: torch.Tensor = torch.from_numpy(((totals - y_mean) / y_std).astype(numpy.float32))

    was: bool = torch.are_deterministic_algorithms_enabled()
    torch.use_deterministic_algorithms(True)
    try:
        torch.manual_seed(params.seed)
        net: SurrogateNet = SurrogateNet(N_FEATURES, params.hidden)
        optimizer: torch.optim.Adam = torch.optim.Adam(net.parameters(), lr=params.lr)
        shuffler: torch.Generator = torch.Generator().manual_seed(params.seed)
        epochs: list[dict[str, Any]] = []
        epoch: int
        for epoch in range(1, params.epochs + 1):
            net.train()
            order: list[int] = torch.randperm(len(xs), generator=shuffler).tolist()
            loss_sum: float = 0.0
            start: int
            for start in range(0, len(order), params.batch):
                idx: list[int] = order[start : start + params.batch]
                x: torch.Tensor
                mask: torch.Tensor
                x, mask = _pad([xs[k] for k in idx])
                loss: torch.Tensor = torch.nn.functional.mse_loss(net(x, mask), ys[idx])
                optimizer.zero_grad()
                torch.autograd.backward(loss)
                optimizer.step()
                loss_sum += float(loss.item()) * len(idx)
            epochs.append({"epoch": epoch, "loss": loss_sum / len(order)})
    finally:
        torch.use_deterministic_algorithms(was)

    meta: dict[str, Any] = {
        "fit_sha256": header["fit_sha256"],
        "fit_chars": header["fit_chars"],
        "sample_chars": header["sample_chars"],
        "sample_chunks": header["sample_chunks"],
        "text_sha256": header["text_sha256"],
        "horizon": horizon,
        "max_keys": header["max_keys"],
        "cost_params": header["cost_params"],
        "penalty_params": header["penalty_params"],
        "features": list(FEATURES),
        "hidden": params.hidden,
        "y_mean": y_mean,
        "y_std": y_std,
        "train_params": dataclasses.asdict(params),
        "seeds_train": sorted({r.seed for r in train}),
        "seeds_holdout": sorted({r.seed for r in holdout}),
        "torch_version": str(torch.__version__),
    }
    surrogate: Surrogate = Surrogate(net, meta, text)
    predicted: list[float] = surrogate.predict_chunked([r.table for r in holdout])
    baseline: list[float] = linear_baseline(train, holdout, counts, costs, horizon)
    report: dict[str, Any] = {
        "format": REPORT_FORMAT,
        "version": 1,
        "model_sha256": None,
        "train_params": meta["train_params"],
        "seeds_train": meta["seeds_train"],
        "seeds_holdout": meta["seeds_holdout"],
        "rows_train": len(train),
        "rows_holdout": len(holdout),
        "train_s": time.monotonic() - started,
        "torch_version": meta["torch_version"],
        "epochs": epochs,
        "holdout": _parts(holdout, predicted),
        "linear": _parts(holdout, baseline),
    }
    return surrogate, report


def _parts(rows: Sequence[DataRow], predicted: Sequence[float]) -> dict[str, Any]:
    out: dict[str, Any] = {"all": metrics(rows, predicted)}
    source: str
    for source in ("trajectory", "random"):
        picked: list[int] = [i for i, r in enumerate(rows) if r.source == source]
        out[source] = metrics([rows[i] for i in picked], [predicted[i] for i in picked])
    return out


def save_surrogate(surrogate: Surrogate, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "format": MODEL_FORMAT,
            "version": MODEL_VERSION,
            "meta": surrogate.meta,
            "state": surrogate.net.state_dict(),
        },
        path,
    )


def _read_blob(path: Path) -> dict[str, Any]:
    try:
        blob: Any = torch.load(path, weights_only=True)
    except Exception as exc:
        raise ValueError(f"{path}: cannot read a surrogate model: {exc}") from exc
    if (
        not isinstance(blob, dict)
        or blob.get("format") != MODEL_FORMAT
        or blob.get("version") != MODEL_VERSION
    ):
        raise ValueError(f"{path}: not a steno-zero surrogate model, version {MODEL_VERSION}")
    return blob


def read_meta(path: Path) -> dict[str, Any]:
    meta: dict[str, Any] = _read_blob(path)["meta"]
    return meta


def load_surrogate(path: Path, text: str) -> Surrogate:
    blob: dict[str, Any] = _read_blob(path)
    meta: dict[str, Any] = blob["meta"]
    if _sha(text) != meta["fit_sha256"]:
        raise ValueError("the text is not the fitness sample the surrogate model was trained on")
    net: SurrogateNet = SurrogateNet(N_FEATURES, meta["hidden"])
    net.load_state_dict(blob["state"])
    return Surrogate(net, meta, text)


def check_compatible(
    meta: dict[str, Any],
    fit_sha256: str,
    horizon: float,
    max_keys: int,
    cost_params: dict[str, Any],
    penalty_params: dict[str, Any],
) -> None:
    mine: dict[str, Any] = {
        "fit_sha256": meta["fit_sha256"][:12],
        "horizon": meta["horizon"],
        "max_keys": meta["max_keys"],
        "cost_params": meta["cost_params"],
        "penalty_params": meta["penalty_params"],
    }
    this: dict[str, Any] = {
        "fit_sha256": fit_sha256[:12],
        "horizon": horizon,
        "max_keys": max_keys,
        "cost_params": cost_params,
        "penalty_params": penalty_params,
    }
    if (
        meta["fit_sha256"] != fit_sha256
        or any(meta[k] != v for k, v in (("horizon", horizon), ("max_keys", max_keys)))
        or _norm(meta["cost_params"]) != _norm(cost_params)
        or _norm(meta["penalty_params"]) != _norm(penalty_params)
    ):
        raise ValueError(
            "surrogate model was trained for "
            + ", ".join(f"{k}={v}" for k, v in mine.items())
            + "; this run has "
            + ", ".join(f"{k}={v}" for k, v in this.items())
        )


def _norm(data: dict[str, Any]) -> dict[str, Any]:
    return {k: list(v) if isinstance(v, tuple) else v for k, v in data.items()}

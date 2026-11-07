"""Record plot."""

import json
from pathlib import Path
from typing import Any

from matplotlib.figure import Figure

LOG_FORMAT: str = "steno-zero/evolve-log"


def read_log(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    line: str
    number: int
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip() == "":
            continue
        try:
            row: Any = json.loads(line)
        except ValueError as exc:
            raise ValueError(f"{path}: line {number} is not JSON") from exc
        if not isinstance(row, dict):
            raise ValueError(f"{path}: line {number} is not an object")
        rows.append(row)
    if not rows or rows[0].get("type") != "run":
        raise ValueError(f"{path}: the first line must be a run line")
    run: dict[str, Any] = rows[0]
    if run.get("format") != LOG_FORMAT or run.get("version") != 1:
        raise ValueError(f"{path}: not a steno-zero evolve log, version 1")
    gens: list[dict[str, Any]] = [r for r in rows if r.get("type") == "generation"]
    if not gens:
        raise ValueError(f"{path}: no generation lines")
    return run, gens


def plot_log(log: Path, out: Path) -> None:
    run: dict[str, Any]
    gens: list[dict[str, Any]]
    run, gens = read_log(log)
    x: list[int] = [g["generation"] for g in gens]
    best: list[float] = [g["best_total"] for g in gens]
    fig: Figure = Figure(figsize=(9, 5))
    ax: Any = fig.subplots()
    ax.plot(x, [g["gen_best_total"] for g in gens], color="tab:blue", alpha=0.3, label="generation best")
    ax.step(x, best, where="post", color="tab:blue", label="record")
    marks: list[int] = [i for i, g in enumerate(gens) if g["record"]]
    ax.plot([x[i] for i in marks], [best[i] for i in marks], "o", color="tab:red", markersize=3)
    ax.axhline(run["rival_total"], color="black", linestyle="--", label="rival")
    ax.set_xlabel("generation")
    ax.set_ylabel("T, s")
    ax.set_title(f"seed {run['seed']}, placeholder prices")
    ax.legend()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, format="png")

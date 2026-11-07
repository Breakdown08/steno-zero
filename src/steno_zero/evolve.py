"""Evolution from scratch: tournament selection, elitism, four mutations."""

import random
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from typing import Any

from steno_zero.alphabet import ALPHABET
from steno_zero.chords import allowed_chords, check_max_keys
from steno_zero.params import DEFAULT_MAX_KEYS, MAX_PIECE_LEN, PenaltyParams
from steno_zero.simulate import Score, evaluate
from steno_zero.table import Table

MUTATIONS: tuple[str, ...] = ("add", "remove", "swap", "move")
SAMPLE_CHARS: int = 60_000
SAMPLE_CHUNKS: int = 20


@dataclass(frozen=True)
class EvolveParams:
    seed: int = 0
    population: int = 32
    generations: int = 300
    elite: int = 2
    tournament: int = 5
    init_extra: int = 20
    max_mutations: int = 3
    max_keys: int = DEFAULT_MAX_KEYS

    def __post_init__(self) -> None:
        if self.population < 2:
            raise ValueError("population must be at least 2")
        if not 0 <= self.elite < self.population:
            raise ValueError("elite must be in 0..population-1")
        if not 1 <= self.tournament <= self.population:
            raise ValueError("tournament must be in 1..population")
        if self.generations < 0:
            raise ValueError("generations must not be negative")
        if self.init_extra < 0:
            raise ValueError("init_extra must not be negative")
        if self.max_mutations < 1:
            raise ValueError("max_mutations must be at least 1")
        check_max_keys(self.max_keys)


@dataclass(frozen=True)
class GenerationRecord:
    generation: int
    best_total: float
    gen_best_total: float
    mean_total: float
    entries: int
    t_char: float
    memory: float
    confusion: float
    record: bool
    evaluations: int


@dataclass(frozen=True)
class EvolveResult:
    best: Table
    score: Score
    history: tuple[GenerationRecord, ...]


def fitness_text(train: str, chars: int, chunks: int = SAMPLE_CHUNKS) -> str:
    if chars < 0:
        raise ValueError("chars must not be negative")
    if chunks < 1:
        raise ValueError("chunks must be at least 1")
    if chars == 0 or chars >= len(train):
        return train
    size: int = chars // chunks
    if size == 0:
        raise ValueError("chars is too small for this number of chunks")
    starts: list[int] = [i * len(train) // chunks for i in range(chunks)]
    return "".join(train[s : s + size] for s in starts)


def draw_piece(text: str, rng: random.Random) -> str:
    if len(text) < 2:
        raise ValueError("text is too short")
    i: int = rng.randint(0, len(text) - 2)
    length: int = rng.randint(2, min(MAX_PIECE_LEN, len(text) - i))
    return text[i : i + length]


def _free_chords(entries: dict[str, int], max_keys: int) -> list[int]:
    used: set[int] = set(entries.values())
    return [c for c in allowed_chords(max_keys) if c not in used]


def _add(entries: dict[str, int], text: str, rng: random.Random, max_keys: int) -> None:
    piece: str = draw_piece(text, rng)
    if piece in entries:
        return
    free: list[int] = _free_chords(entries, max_keys)
    if free:
        entries[piece] = rng.choice(free)


def random_table(text: str, rng: random.Random, extra: int, max_keys: int = DEFAULT_MAX_KEYS) -> Table:
    if extra < 0:
        raise ValueError("extra must not be negative")
    chords: list[int] = rng.sample(allowed_chords(max_keys), len(ALPHABET))
    entries: dict[str, int] = dict(zip(ALPHABET, chords, strict=True))
    i: int
    for i in range(rng.randint(0, extra)):  # noqa: B007
        _add(entries, text, rng, max_keys)
    return Table(entries)


def mutate(table: Table, kind: str, text: str, rng: random.Random, max_keys: int = DEFAULT_MAX_KEYS) -> Table:
    if kind not in MUTATIONS:
        raise ValueError(f"unknown mutation {kind!r}")
    check_max_keys(max_keys)
    entries: dict[str, int] = table.entries
    pieces: list[str] = list(entries)
    if kind == "add":
        _add(entries, text, rng, max_keys)
    elif kind == "remove":
        long: list[str] = [p for p in pieces if len(p) >= 2]
        if not long:
            return table
        del entries[rng.choice(long)]
    elif kind == "swap":
        a: str
        b: str
        a, b = rng.sample(pieces, 2)
        entries[a], entries[b] = entries[b], entries[a]
    else:
        free: list[int] = _free_chords(entries, max_keys)
        if not free:
            return table
        entries[rng.choice(pieces)] = rng.choice(free)
    return Table(entries)


_STATE: dict[str, Any] = {}


def _init_worker(text: str, costs: Sequence[int], penalty: PenaltyParams, horizon: float) -> None:
    _STATE["args"] = (text, costs, penalty, horizon)


def _eval_worker(table: Table) -> Score:
    text: str
    costs: Sequence[int]
    penalty: PenaltyParams
    horizon: float
    text, costs, penalty, horizon = _STATE["args"]
    return evaluate(text, table, costs, penalty, horizon)


def _evolve(
    text: str,
    costs: Sequence[int],
    penalty: PenaltyParams,
    horizon: float,
    params: EvolveParams,
    run_map: Callable[[list[Table]], list[Score]],
    on_generation: Callable[[GenerationRecord], None] | None,
) -> EvolveResult:
    rng: random.Random = random.Random(params.seed)
    pop: list[Table] = [
        random_table(text, rng, params.init_extra, params.max_keys) for _ in range(params.population)
    ]
    prev: dict[Table, Score] = {}
    best: Table | None = None
    best_score: Score | None = None
    history: list[GenerationRecord] = []
    evaluations: int = 0
    gen: int
    for gen in range(params.generations + 1):
        cache: dict[Table, Score] = {}
        fresh: list[Table] = []
        t: Table
        for t in pop:
            if t in cache:
                continue
            if t in prev:
                cache[t] = prev[t]
            elif t not in fresh:
                fresh.append(t)
        scores: list[Score] = run_map(fresh) if fresh else []
        s: Score
        for t, s in zip(fresh, scores, strict=True):
            cache[t] = s
        evaluations += len(fresh)
        totals: list[float] = [cache[t].total for t in pop]
        order: list[int] = sorted(range(len(pop)), key=lambda k: (totals[k], k))
        top: int = order[0]
        improved: bool = best_score is None or totals[top] < best_score.total
        if improved:
            best, best_score = pop[top], cache[pop[top]]
        assert best is not None and best_score is not None
        record: GenerationRecord = GenerationRecord(
            generation=gen,
            best_total=best_score.total,
            gen_best_total=totals[top],
            mean_total=sum(totals) / len(totals),
            entries=len(best),
            t_char=best_score.t_char,
            memory=best_score.memory,
            confusion=best_score.confusion,
            record=improved,
            evaluations=evaluations,
        )
        history.append(record)
        if on_generation is not None:
            on_generation(record)
        if gen == params.generations:
            break
        nxt: list[Table] = [pop[k] for k in order[: params.elite]]
        while len(nxt) < params.population:
            contenders: list[int] = rng.sample(range(len(pop)), params.tournament)
            parent: Table = pop[min(contenders, key=lambda k: (totals[k], k))]
            kind: str
            n: int
            for n in range(rng.randint(1, params.max_mutations)):  # noqa: B007
                kind = rng.choice(MUTATIONS)
                parent = mutate(parent, kind, text, rng, params.max_keys)
            nxt.append(parent)
        prev = cache
        pop = nxt
    assert best is not None and best_score is not None
    return EvolveResult(best, best_score, tuple(history))


def evolve(
    text: str,
    costs: Sequence[int],
    penalty: PenaltyParams,
    horizon: float,
    params: EvolveParams,
    workers: int = 1,
    on_generation: Callable[[GenerationRecord], None] | None = None,
) -> EvolveResult:
    if len(text) < 2:
        raise ValueError("text is too short")
    if workers < 1:
        raise ValueError("workers must be at least 1")
    if workers == 1:

        def run_serial(tables: list[Table]) -> list[Score]:
            return [evaluate(text, t, costs, penalty, horizon) for t in tables]

        return _evolve(text, costs, penalty, horizon, params, run_serial, on_generation)
    executor: Any
    with ProcessPoolExecutor(
        max_workers=workers, initializer=_init_worker, initargs=(text, costs, penalty, horizon)
    ) as executor:

        def run_pool(tables: list[Table]) -> list[Score]:
            return list(executor.map(_eval_worker, tables))

        return _evolve(text, costs, penalty, horizon, params, run_pool, on_generation)

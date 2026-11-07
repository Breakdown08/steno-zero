# steno-zero

A test bench for one question: which table "piece of text -> chord" on ten keys would evolution find, with no ready-made human system to start from? This repository is the bench: a Russian corpus, a typing simulator that scores a table by `T = H * t_char + M`, and a frequency-based rival that any evolved table has to beat. Evolution from scratch (tournament selection, elitism, four mutations) writes a record log and a plot.

**Chord prices and the memory penalty `M` are placeholders, not measurements.** Every number in `src/steno_zero/params.py` is a stub until real values are measured on a keyboard that holds ten simultaneous keys.

## What it does

- Alphabet of 41 symbols: 33 Russian letters, space and `- . , ! ? : ;`. Text is normalised (lower case, dashes unified, everything else dropped).
- Chords are 1..1023 over ten keys (five fingers per hand). A table maps pieces of up to 8 symbols to distinct chords and must contain every alphabet symbol, so any text can be typed and decoded without loss.
- The simulator segments text greedily (longest matching piece first, like a person would) and sums chord prices. `M` charges for each table entry, more for rarely used ones.
- The rival gives the most frequent symbols the cheapest chords. For single symbols with chord prices independent of the symbol this is the exact optimum (checked against brute force in the tests).

## Run

Requires Python 3.14 and [uv](https://docs.astral.sh/uv/).

```
uv sync
uv run steno-zero corpus fetch          # first step: download the pinned corpus, check SHA-256
uv run steno-zero rival --out rival.json
uv run steno-zero evaluate --table rival.json
uv run steno-zero rival --part test     # train / test / all, split 90% / 10%
```

```
uv run steno-zero evolve                # defaults: seed 0, 32 tables, 300 generations, all cores
uv run steno-zero plot --log runs/seed-0/log.jsonl   # writes runs/seed-0/records.png
uv run steno-zero evolve --seed 1 --workers 4 --out runs/other
uv run steno-zero evaluate --table runs/seed-0/best.json
```

`evolve` writes `log.jsonl` (one line per generation) and `best.json` (the best table) to `runs/seed-<seed>/`. Same seed and parameters give byte-identical files for any `--workers`. `runs/` is not in git.

Each command prints a one-line JSON summary: `chars, chords, entries, t_char, memory, total`.

Checks: `uv run ruff check`, `uv run ruff format --check`, `uv run ty check`, `uv run mypy`, `uv run pytest`. The tests do not use the network.

## Corpus

Stories by Tolstoy and Chekhov from the Russian Wikisource (https://ru.wikisource.org), modern spelling, license `PD-old-70` (public domain). Revisions are pinned by `oldid` in `data/corpus/sources.json`, together with the SHA-256 of the resulting text. Wikisource notes (CC BY-SA) are stripped; only the authors' text is kept. The text itself is not in git: `corpus fetch` downloads it to `data/corpus/classics.txt` (about 400 000 symbols, 10 works). `tests/data/fragment.txt` is a small excerpt used only as a test fixture.

## Measured

Command: `uv run steno-zero rival` (full corpus, 402 666 symbols, default horizon `H = 1 000 000` symbols, placeholder prices):

| value | result |
|---|---|
| `t_char` | 0.2213 s per symbol |
| `M` | 2534.0 s |
| `T` | 223 803 s |

The run takes about 0.2 s. These numbers describe the placeholder cost model, not a real keyboard.

## Evolution result

Command: `uv run steno-zero evolve` (seed 0, population 32, 300 generations, fitness on 60 000 symbols sampled in 20 chunks over train, default horizon, **placeholder prices and `M`**). Entries: 111 (the rival has 41).

| `T`, s | evolved | rival |
|---|---|---|
| fitness sample (60 000 symbols) | 202 388 | 223 782 |
| train | 202 485 | 223 777 |
| test | 203 462 | 224 051 |

Evolution beats the rival by 9.5 % on train and 9.2 % on test. These numbers describe the placeholder cost model, not a real keyboard.

Run time on the 22-thread Core Ultra 7 155H (6 P-cores): `--workers 1` 311 s, `--workers 6` 70 s, `--workers 11` 54 s, `--workers 22` 45 s (6.9x faster than one process). The logs and `best.json` of all four runs are byte-identical (`cmp`).

## Not supported

- Crossover of tables and resuming an interrupted run.
- The neural network.
- Chord prices that depend on the previous chord, key press errors, measured prices.
- Memory penalty stages beyond a per-entry cost with a rarity surcharge.
- Capital letters, digits, quotes, brackets, Latin letters and line breaks: normalisation drops them.

## License

Apache-2.0, see `LICENSE`. The corpus texts are in the public domain.

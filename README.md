# steno-zero

A test bench for one question: which table "piece of text -> chord" on ten keys would evolution find, with no ready-made human system to start from? This repository is the bench: a Russian corpus, a typing simulator that scores a table by `T = H * t_char + M + C`, and a frequency-based rival that any evolved table has to beat. Evolution from scratch (tournament selection, elitism, four mutations) writes a record log and a plot.

**Chord prices, the memory penalty `M` and the confusion penalty `C` are placeholders, not measurements.** Every number in `src/steno_zero/params.py` is a stub until real values are measured on a keyboard that holds ten simultaneous keys.

## What it does

- Alphabet of 41 symbols: 33 Russian letters, space and `- . , ! ? : ;`. Text is normalised (lower case, dashes unified, everything else dropped).
- Chords are 1..1023 over ten keys (five fingers per hand). A table maps pieces of up to 8 symbols to distinct chords and must contain every alphabet symbol, so any text can be typed and decoded without loss.
- The simulator segments text greedily (longest matching piece first, like a person would) and sums chord prices. `M` charges for each table entry, more for rarely used ones. `C` is the motor confusion: a finger slip turns a chord into a neighbour chord (one key more or less); if the neighbour is another entry of the table, a wrong piece appears and the person spends `confusion_s` seconds to fix it. `C` grows with the use counts of both entries of a neighbouring pair. `--confusion-s 0` switches it off, and then `T`, `M` and `t_char` are bit-identical to the numbers without `C`.
- The rival gives the most frequent symbols the cheapest chords. For single symbols with chord prices independent of the symbol this is the exact optimum for the typing price (checked against brute force in the tests); it pays for confusion like any other table.

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

Each command prints a one-line JSON summary: `chars, chords, entries, t_char, memory, confusion, total`. `rival`, `evaluate` and `evolve` take `--confusion-s S` (default 2.0).

Checks: `uv run ruff check`, `uv run ruff format --check`, `uv run ty check`, `uv run mypy`, `uv run pytest`. The tests do not use the network.

## Corpus

Stories by Tolstoy and Chekhov from the Russian Wikisource (https://ru.wikisource.org), modern spelling, license `PD-old-70` (public domain). Revisions are pinned by `oldid` in `data/corpus/sources.json`, together with the SHA-256 of the resulting text. Wikisource notes (CC BY-SA) are stripped; only the authors' text is kept. The text itself is not in git: `corpus fetch` downloads it to `data/corpus/classics.txt` (about 400 000 symbols, 10 works). `tests/data/fragment.txt` is a small excerpt used only as a test fixture.

## Measured

Command: `uv run steno-zero rival --part train` (train, 362 399 symbols, `H = 1 000 000` symbols, placeholder prices), then `evaluate --table rival.json --part train` (add `--confusion-s 0` to switch the penalty off). Entries: 41.

| value | with `C` (default) | without confusion penalty (`--confusion-s 0`) |
|---|---|---|
| `t_char` | 0.2212 s | 0.2212 s |
| `M` | 2534.2 s | 2534.2 s |
| `C` | 20 881 s | 0 |
| `T` | 244 658 s | 223 777 s |

The earlier full-corpus numbers (402 666 symbols, without confusion penalty): `t_char` 0.2213 s, `M` 2534.0 s, `T` 223 803 s. These numbers describe the placeholder cost model, not a real keyboard.

## Evolution result

Commands (seed 0, population 32, 300 generations, fitness on 60 000 symbols sampled in 20 chunks over train, default horizon, **placeholder prices, `M` and `C`**):

```
uv run steno-zero evolve --out runs/conf-default                    # with C
uv run steno-zero evolve --confusion-s 0 --out runs/c0              # without C
uv run steno-zero evaluate --table runs/conf-default/best.json --part train   # and --part test, --confusion-s 0
```

`T`, s, on train / test (`t_char` and `M` and `C` are parts of `T`; "`T` without `C`" is `--confusion-s 0`):

| table | entries (multi-symbol) | `T` without `C` train / test | `C` train / test | `T` train / test |
|---|---|---|---|---|
| rival | 41 (0) | 223 777 / 224 051 | 20 881 / 20 726 | 244 658 / 244 776 |
| evolved without `C` (`--confusion-s 0`) | 111 (70) | 202 485 / 203 462 | 12 550 / 12 556 | 215 035 / 216 019 |
| evolved with `C` (default) | 100 (59) | 207 348 / 208 176 | 6 584 / 6 635 | 213 932 / 214 811 |

The table with the penalty loses 2.4 % of pure typing time against the table without it (207 348 vs 202 485 on train) and halves the confusion (6 584 vs 12 550); in total `T` it is ahead by 0.5 % on train. Against the rival it is 12.6 % ahead in `T` on train and 12.2 % on test. The run without `C` is byte-identical in `best.json` to the earlier run of the previous milestone (`cmp`).

Fitness sample (60 000 symbols), with `C`: evolved 213 480, rival 244 664.

Run time on the 22-thread Core Ultra 7 155H (6 P-cores), default `--workers`: 45.5 s with `--confusion-s 0`, 47.4 s with `C`.

### Long run

Command: `uv run steno-zero evolve --generations 1000 --sample-chars 0 --workers 22 --out runs/long-g1000-full-confusion` (13 min 6 s); the earlier run is `runs/long-g1000-full` (without `C`). Train / test:

| table | entries (multi-symbol) | `t_char`, s | `M`, s | `C` | `T` without `C` | `T` |
|---|---|---|---|---|---|---|
| long without `C` | 144 (103) | 0.1643 / 0.1669 | 9 466 / 9 909 | 14 798 / 14 911 | 173 799 / 176 764 | 188 597 / 191 675 |
| long with `C` | 147 (106) | 0.1736 / 0.1749 | 9 625 / 10 366 | 6 196 / 6 320 | 183 272 / 185 236 | 189 468 / 191 557 |

With the penalty the long run gives up 5.4 % of pure typing time on train and cuts the confusion by 58 %; in total `T` the two tables are within 0.5 % of each other. These numbers describe the placeholder cost model, not a real keyboard.

## Not supported

- Crossover of tables and resuming an interrupted run.
- The neural network.
- Chord prices that depend on the previous chord, slips of more than one key, per-finger slip rates, measured slip rates, measured prices.
- Memory penalty stages beyond a per-entry cost with a rarity surcharge.
- Capital letters, digits, quotes, brackets, Latin letters and line breaks: normalisation drops them.

## License

Apache-2.0, see `LICENSE`. The corpus texts are in the public domain.

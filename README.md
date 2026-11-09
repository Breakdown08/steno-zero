# steno-zero

A test bench for one question: which table "piece of text -> chord" on ten keys would evolution find, with no ready-made human system to start from? This repository is the bench: a Russian corpus, a typing simulator that scores a table by `T = H * t_char + M + C`, and a frequency-based rival that any evolved table has to beat. Evolution from scratch (tournament selection, elitism, four mutations) writes a record log and a plot.

**Chord prices, the memory penalty `M` and the confusion penalty `C` are placeholders, not measurements.** Every number in `src/steno_zero/params.py` is a stub until real values are measured on a keyboard that holds ten simultaneous keys.

## What it does

- Alphabet of 41 symbols: 33 Russian letters, space and `- . , ! ? : ;`. Text is normalised (lower case, dashes unified, everything else dropped).
- Chords are 1..1023 over ten keys (five fingers per hand). A chord is registered when all its keys are released, as the set of keys that were held down together; the order of presses and the intermediate states do not matter. So a table needs no rule about prefixes of chords: that is the input device's job, not the table's. A table maps pieces of up to 8 symbols to distinct chords and must contain every alphabet symbol, so any text can be typed and decoded without loss.
- The simulator segments text greedily (longest matching piece first, like a person would) and sums chord prices. `M` charges for each table entry, more for rarely used ones. `C` is the motor confusion: a finger slip turns a chord into a neighbour chord (one key more or less); if the neighbour is another entry of the table, a wrong piece appears and the person spends `confusion_s` seconds to fix it. `C` grows with the use counts of both entries of a neighbouring pair. `--confusion-s 0` switches it off, and then `T`, `M` and `t_char` are bit-identical to the numbers without `C`.
- A table uses only chords of at most `K` keys (default `K = 6`, flag `--max-keys`), because ordinary keyboards often pass at most six simultaneously held keys (checked with `evtest` on three keyboards: a laptop, a split keyboard on RMK and an external keyboard on Vial). `--max-keys 10` lifts the limit and gives the earlier results byte for byte. `K` must be in 2..10. `evolve` and `rival` produce only chords of up to `K` keys; `evaluate` and `trainer export` refuse a table that breaks the limit and name the flag, so tables of earlier runs are evaluated with `--max-keys 10`.
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

Each command prints a one-line JSON summary: `chars, chords, entries, t_char, memory, confusion, total`. `rival`, `evaluate` and `evolve` take `--confusion-s S` (default 2.0); `rival`, `evaluate`, `evolve` and `trainer export` take `--max-keys K` (default 6). The first line of `log.jsonl` records `max_keys` (log version 3).

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

Commands (seed 0, population 32, 300 generations, fitness on 60 000 symbols sampled in 20 chunks over train, default horizon, `K = 6`, **placeholder prices, `M` and `C`**):

```
uv run steno-zero evolve --out runs/k6                              # with C, K = 6
uv run steno-zero evolve --max-keys 10 --out runs/k10               # with C, no key limit
uv run steno-zero evaluate --table runs/k6/best.json --part train   # and --part test, --confusion-s 0
uv run steno-zero evaluate --table runs/conf-default/best.json --part train --max-keys 10
```

`T`, s, on train / test (`t_char`, `M` and `C` are parts of `T`; "`T` without `C`" is `--confusion-s 0`). The rows marked "without key limit" are tables of earlier runs (`runs/conf-default`, `runs/c0`), evaluated with `--max-keys 10`; they have chords of up to 9 keys and cannot be typed on a keyboard that passes 6.

| table | entries (multi-symbol) | `T` without `C` train / test | `C` train / test | `T` train / test |
|---|---|---|---|---|
| rival | 41 (0) | 223 777 / 224 051 | 20 881 / 20 726 | 244 658 / 244 776 |
| evolved, `K = 6` (default) | 122 (81) | 197 905 / 199 240 | 8 852 / 8 893 | 206 758 / 208 133 |
| evolved with `C`, without key limit (`--max-keys 10`) | 100 (59) | 207 348 / 208 176 | 6 584 / 6 635 | 213 932 / 214 811 |
| evolved without `C` (`--confusion-s 0`), without key limit | 111 (70) | 202 485 / 203 462 | 12 550 / 12 556 | 215 035 / 216 019 |

The `K = 6` table is 15.5 % ahead of the rival in `T` on train and 15.0 % on test. The run with `--max-keys 10` is byte-identical in `best.json` to `runs/conf-default` (`cmp`), so the limit changes nothing when lifted. The `K = 6` and the unlimited runs follow different search paths (the lists the random generator chooses from have different lengths), so their difference is the difference of two single runs with one seed, not the price of the limit.

Fitness sample (60 000 symbols), `K = 6`: evolved 206 647, rival 244 664.

Run time on the 22-thread Core Ultra 7 155H (6 P-cores), default `--workers`, wall clock including start-up: 49.6 s with `K = 6`, 44.9 s with `--max-keys 10`.

### Long run

Command: `uv run steno-zero evolve --generations 1000 --sample-chars 0 --workers 22 --out runs/long-g1000-full-confusion-k6` (13 min 5 s); the earlier runs are `runs/long-g1000-full-confusion` (with `C`) and `runs/long-g1000-full` (without `C`), evaluated with `--max-keys 10`. Train / test:

| table | entries (multi-symbol) | `t_char`, s | `M`, s | `C` | `T` without `C` | `T` |
|---|---|---|---|---|---|---|
| long with `C`, `K = 6` | 159 (118) | 0.1660 / 0.1662 | 10 445 / 10 611 | 7 812 / 7 778 | 176 483 / 176 787 | 184 295 / 184 565 |
| long with `C`, without key limit | 147 (106) | 0.1736 / 0.1749 | 9 625 / 10 366 | 6 196 / 6 320 | 183 272 / 185 236 | 189 468 / 191 557 |
| long without `C`, without key limit | 144 (103) | 0.1643 / 0.1669 | 9 466 / 9 909 | 14 798 / 14 911 | 173 799 / 176 764 | 188 597 / 191 675 |

The `K = 6` table has chords of up to 6 keys (distribution by number of keys 1..6: 10, 17, 58, 36, 27, 11); the unlimited one has two chords on 7 keys. These numbers describe the placeholder cost model, not a real keyboard.

## Trainer

A static browser page for typing phrases with a table on an ordinary keyboard. It exists to measure how long a person takes per chord and how often they hit a neighbouring chord; the prices in `CostParams`, `slip_prob` and `confusion_s` are still placeholders. Open `docs/index.html` from disk, or serve the `docs/` folder with GitHub Pages. The page has no build step, no npm and no external links; the interface is in Russian.

Rebuild `docs/data.js` (it is committed, because GitHub Pages needs it and the corpus is not in git):

```
uv run steno-zero rival --part train --out runs/rival-train.json
uv run steno-zero trainer export --table rival=runs/rival-train.json \
    --table evolved=runs/long-g1000-full-confusion-k6/best.json
```

The first table is the one opened by default; `index.html?table=evolved` picks another. `export` takes 200 home phrases from the train part of the corpus and 100 exam phrases from the test part (the two sets do not intersect), cuts each phrase with the same greedy segmentation as the simulator and writes everything, layout included, to one file. Running it again gives the same bytes. Options: `--corpus`, `--min-len`, `--max-len`, `--home-limit`, `--exam-limit`, `--exam-size`, `--out`.

Layout: key `i` is bit `i` of the chord. The page reads `KeyboardEvent.code`, so the OS keyboard layout does not matter.

| i | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
|---|---|---|---|---|---|---|---|---|---|---|
| key | `a` | `s` | `d` | `f` | `v` | `n` | `j` | `k` | `l` | `;` |
| finger | left little | left ring | left middle | left index | left index, down | right index, down | right index | right middle | right ring | right little |

The help key is the physical `/` key (`Slash`, `.` on a Russian layout).

A chord fires when all its keys are released: press the keys together, let go, and the chord is the set of keys held since the first press. A wrong chord is not accepted and the piece must be repeated (strict mode); there is no backspace.

Two modes. Home: phrase after phrase, help on the `/` key, a hint for the next piece, nothing is recorded. Exam (the "Экзамен" button): 5 random phrases from the exam set, no help and no hint, a timer that starts at the first key press. **Measurements are written only in the exam.** At the end the page shows the time, symbols per minute and misses, and "Скачать журнал" saves a JSON log (`steno-zero-<session>.json`, format `steno-zero/trainer-log`, version 1: session, table and its SHA-256, start and finish, user agent, the largest number of keys held at once, phrase indices and one record `phrase, pos, target, typed, down_ms, up_ms` per fired chord). An aborted exam leaves nothing.

```
uv run steno-zero trainer stats runs/trainer/*.json --out runs/trainer/stats.json
```

`trainer stats` prints one JSON line per session (time, symbols per minute, misses) and a summary line (misses by a neighbouring chord or otherwise, `slip_prob`, the median interval between clean consecutive chords). With `--out` the file also holds the time and the misses of every chord. `slip_prob` is the neighbour misses divided by the number of neighbours of all targets, the same quantity as `PenaltyParams.slip_prob`. These numbers are measurements of one person on one keyboard: a keyboard may lose keys pressed together (the page shows the largest number held at once; the three keyboards checked pass at most 6, hence the default `K = 6`), and the figures are not a general property of chords.

### Calibration and random chords

The exam measures only the 41-159 chords of one table, but a price model has to cover every chord the keyboard can type. So the page has two more modes, both written to separate logs.

**Keyboard facts.** The laptop passes at most 6 keys held together, and its matrix has no diodes, so some triples are swallowed: with `f v` held, `k` (also `l`, `;`) never reaches the kernel, while `f v j` passes. A keyboard on Vial sees all 10 keys in the matrix but hands the browser at most 6 (a 6KRO report). A swallowed key looks in a log exactly like a human slip (the same chord without one key), so the keyboard is calibrated once before any measurement.

**Calibration** ("Калибровка клавиатуры"): the 45 pairs and 120 triples, each up to three attempts (about 5-6 minutes), and the page saves a `steno-zero/keyboard-calibration` log. Then

```
uv run steno-zero keyboard profile calibration.json --name laptop   # writes data/keyboards/laptop.json
```

builds a **keyboard profile**, the list of unavailable combinations. A combination that never passed is blocked; only minimal blocked combinations are kept (a triple holding a blocked pair is not listed), and `unclear` marks one where an extra key arrived at least once (it may be a human slip, but it is excluded anyway; calibrate again and compare). A matrix without diodes blocks three keys in three corners of a rectangle, so a chord is unavailable exactly when it holds a blocked pair or triple; this is an assumption about the firmware, not a checked fact, and `price fit` lists suspicious chords as a safety net. The profile file is committed (`data/keyboards/`, no user agent in it) and is read by `read_profile`, which accepts blocked combinations of any length >= 2, so a suspicious chord can be added by hand. `--max-keys` only changes the `available` number of the summary.

**Random chords** ("Случайные аккорды"): the page shows a chord on a ten-key scheme with its label, you press it, and the page writes the time and the miss. A miss is not repeated: the wrong chord flashes red and the next one comes at once. The sequence is built in Python and played by the page, so all checked logic stays out of JS:

```
uv run steno-zero trainer drill --keyboard data/keyboards/laptop.json   # writes docs/drill.js
```

`docs/drill.js` holds 100 blocks of 100 chords (seed 0, `--max-keys 6`), the keyboard name with its SHA-256 and the calibration queue, and is rebuilt byte for byte from these parameters and the profile in `data/keyboards/`. The committed file is built without a profile until the laptop is calibrated; the page then warns that chords swallowed by the keyboard will give false misses. The sampling is deliberately not uniform over chords: every block is balanced by the number of keys, then by the number of keys on the left hand, and inside a stratum chords come from a shuffled deck, so one-handed chords with many keys are measured too (small strata repeat often by design). Only available chords are drawn and no chord repeats in a row. `index.html?block=N` replays block `N`; otherwise a block is random.

A block log has the format `steno-zero/drill-log`, version 1: session `drill-<block>-<start>`, seed, block, `max_keys`, the keyboard (`name`, `sha256`, or `null`), start and finish, user agent, the largest number of keys held and one record `i, target, typed, shown_ms, down_ms, up_ms` per chord (`performance.now()` times; `shown_ms` is taken when the scheme is already in the page).

## Chord prices

```
uv run steno-zero price fit runs/drill/*.json --keyboard data/keyboards/laptop.json --out runs/price
```

`price fit` reads the logs of random chords into a pandas table (one row per presentation, the first 5 of each session dropped as warm-up) and writes `prices.json` and `report.json`. Features of a chord (19): the number of keys, keys per hand, both hands, one flag per key, both index keys of a hand, adjacent pressed keys, the finger span and the finger holes per hand, and a mirrored left/right shape. The target is `total` (release minus display) or `motor` (release minus first press); a miss is not a time, and slower rows than `--max-ms` are dropped.

The baseline (the mean time by the number of keys), Ridge and gradient boosting are compared by 5-fold `GroupKFold` **by chord**, so every score is for chords the model has not seen. Metrics: MAE, R2 and the mean per-chord error. The miss probability is compared in the same way (a smoothed rate by the number of keys against logistic regression, log loss and Brier score). `auto` picks the model with the smallest MAE. `prices.json` lists **all** chords allowed by `--max-keys`; the chords unavailable on the keyboard profile have `available: false` and `null` time and miss probability. `report.json` also has the Ridge coefficients, per-session medians (drift) and `suspect_chords`: chords whose presentations all missed, each time with a strict subset of the keys, which may be a key the keyboard swallows and is not in the profile.

Logs taken on different profiles (or some with and some without) are never mixed, and the profile given to `--keyboard` must be the one recorded in the logs. The human slip and a swallowed key cannot be told apart from a log alone, which is why the profile exists. On synthetic data with a known dependence Ridge recovers it and beats the baseline several times over (the tests check it); **there are no numbers from live measurements yet**, and the prices are not connected to the evolution. The time of a random chord includes recognising the scheme, which fluent typing does not have, so it is not yet an absolute price.

## Not supported

- Crossover of tables and resuming an interrupted run.
- The neural network.
- Chord prices that depend on the previous chord, slips of more than one key, per-finger slip rates, measured slip rates, measured prices (the `price fit` model exists, but there are no live measurements and nothing feeds them to the evolution), calibration of drill times to fluent typing.
- Memory penalty stages beyond a per-entry cost with a rarity surcharge.
- Free typing with backspace in the trainer, an estimate of `confusion_s` and measurements in the home mode.
- Key-blocking check beyond pairs and triples, and an evolution that avoids chords blocked by a keyboard profile.
- Capital letters, digits, quotes, brackets, Latin letters and line breaks: normalisation drops them.

## License

Apache-2.0, see `LICENSE`. The corpus texts are in the public domain.

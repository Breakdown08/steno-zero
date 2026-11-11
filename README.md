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

## Surrogate

A small PyTorch network predicts `T` of a table without running the simulator and works as a **filter** in the evolution: each generation produces `--oversample` times more offspring than needed, the network keeps the best ones, and only those go to the exact simulator. The population, every `T` in the log and the final `T` are exact; a predicted `T` never enters the population. The model is valid only for the corpus sample, prices, penalties, horizon and `--max-keys` it was trained on; the commands refuse any other.

Install torch (the CPU wheel from `download.pytorch.org/whl/cpu`, about 200 MB, no CUDA; `uv sync` for development installs it too, since it is in the `dev` group):

```
uv sync --extra surrogate
```

Without torch everything else works as before (`evolve`, `surrogate data`); the other commands say how to install it.

```
uv run steno-zero surrogate data                                       # seeds 1000..1003: evolution trajectories + 500 random tables each
uv run steno-zero surrogate train --data runs/surrogate/data.jsonl     # writes runs/surrogate/model.pt and model.json
uv run steno-zero evolve --surrogate runs/surrogate/model.pt --oversample 4 --out runs/sur
uv run steno-zero surrogate compare --model runs/surrogate/model.pt    # seeds 0..2, with and without the filter
```

How it works. A table is a set of (piece, chord) entries of varying size, and `T` is nearly additive over entries, so the encoding is DeepSets: a small network over each entry (16 features: ten key bits, number of keys, chord price, piece length, log use count in the sample, number of neighbour chords in the table, a constant 1), a masked sum over entries, and a second network on the sum (9 473 parameters at `--hidden 64`). The result does not depend on the order of entries or on padding. The loss is MSE on the standardised `T`, the optimiser is Adam, the model after the last epoch is kept (no epoch selection on held-out data). The data are split **by seed**: the last seed is held out entirely, because neighbouring generations of one trajectory are almost the same table and a split by rows would leak. The seeds of `surrogate compare` (0..2) are not in the data (1000..1003).

Metrics on the held-out seed. `generation_spearman` is the main one: the mean Spearman correlation inside one generation of the held-out trajectory, because the filter compares siblings of one generation. The plain `spearman` over all rows is inflated by the gap between early and late generations and is given for reference; MAE alone says little about order. The linear baseline is least squares on the entry-summed features.

Measured (22 threads, Core Ultra 7 155H, defaults, torch 2.15.0+cpu, one thread for the network):

| metric, held-out seed 1003 | network | linear |
|---|---|---|
| `generation_spearman`, trajectory | 0.657 | 0.272 |
| `spearman`, all rows | 0.995 | 0.980 |
| `spearman`, 500 random tables | 0.739 | -0.075 |
| MAE, s (trajectory) | 3 113 | 8 745 |

The network beats the linear baseline on every metric, most clearly on order inside a generation. 0.657 is far from a perfect ranking: the filter is a noisy one.

Cost: `surrogate data` 205 s (38 003 rows, 54 MB, in `runs/`, not in git), `surrogate train` 157 s (`train_s`, 28 508 rows, 30 epochs).

`surrogate compare` (3 seeds, 300 generations, population 32, `--oversample 4`, 6 runs in 5 min). "Target" is the final `T` of the run without the filter, same seed:

| seed | final `T`, s: no filter / filter | exact evaluations to target: no filter / filter | seconds to target: no filter / filter |
|---|---|---|---|
| 0 | 206 647 / 193 212 | 9 004 / 5 040 | 44.9 / 31.3 |
| 1 | 213 191 / 192 814 | 8 853 / 3 825 | 47.9 / 23.6 |
| 2 | 211 591 / 192 763 | 8 975 / 3 988 | 49.6 / 24.4 |

Speed-up in exact evaluations: 1.79, 2.31, 2.25 (median 2.25); in seconds: 1.43, 2.03, 2.03 (median 2.03); the filter reached the target in all 3 seeds, so by the strict rule (median above 1 and the target reached in every seed) it is faster, by evaluations and by time. At the same number of generations the filtered runs end 6.5 to 9.6 % lower in `T` (`final_ratios` 0.935, 0.904, 0.911). A full 300-generation run with the filter takes about 3 s longer than without it (52.7 s against 44.9 to 49.7 s) because candidate generation, features and the network run in the main process; the gain is that it gets to the same `T` in about half the time. This is a result of three seeds on one corpus with placeholder prices, not a general claim. Data and training cost 6 minutes once; at about 20 to 25 s saved per run to the same `T`, that pays back after roughly 15 runs of evolution with the same prices and corpus, and never if the prices change (the model must be retrained).

Determinism. The same data, parameters, seed, torch version and machine give equal weight tensors (`torch.equal`), equal predictions, and byte-identical `log.jsonl` and `best.json` of `evolve --surrogate` for any `--workers`. Not promised: equal weights on another CPU, OS or torch version (BLAS and oneDNN pick different kernels) and byte-identical `model.pt`. The `surrogate data` file is byte-identical for any `--workers` and `PYTHONHASHSEED`. The log of a run with a surrogate has `version: 4` with two extra keys in the first line, `surrogate_sha256` and `oversample`; without `--surrogate` the log is as before.

## Fingers and layouts

A chord is a set of fingers, not of letters. Bit `i` of a chord is the finger `FINGERS[i]`:

| bit | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
|---|---|---|---|---|---|---|---|---|---|---|
| finger | `L4` | `L3` | `L2` | `L1` | `L0` | `R0` | `R1` | `R2` | `R3` | `R4` |
| meaning | left little | left ring | left middle | left index | left thumb | right thumb | right index | right middle | right ring | right little |

The digits count like a guitar fingering: the thumb is `0` because it presses from below, the four fingers above the keys are numbered in a row from the index (`1`) to the little finger (`4`). Mirrored fingers share a digit (`L1` and `R1`), which is what the price feature `mirror` looks at. A chord label is the finger names in bit order: `L1 R1` is bit 3 and bit 6. Tables, logs, reports and the page speak in fingers.

Which physical key a finger presses is data, not code: a layout is a file `data/layouts/NAME.json` (format `steno-zero/layout`, version 1) with ten items `finger`, `code` (a `KeyboardEvent.code`, so the OS keyboard layout does not matter) and `label` (what the page shows on the fingertip). The current layout is `qwerty-vm`, the right thumb on `KeyM`:

| finger | `L4` | `L3` | `L2` | `L1` | `L0` | `R0` | `R1` | `R2` | `R3` | `R4` |
|---|---|---|---|---|---|---|---|---|---|---|
| key | `KeyA` | `KeyS` | `KeyD` | `KeyF` | `KeyV` | `KeyM` | `KeyJ` | `KeyK` | `KeyL` | `Semicolon` |

To add a layout, put a file into `data/layouts/` and run `uv run steno-zero trainer setups`. That rebuilds `docs/setups.js`, the list of setups (a layout, with a keyboard profile that covers its keys, if there is one) the page chooses from (`index.html?setup=NAME`). No code changes, and `docs/drill.js` and `docs/data.js` are not rebuilt. The help key `Slash` and the skip key `Escape` cannot be used by a layout.

## Trainer

A static browser page for typing phrases with a table on an ordinary keyboard. It exists to measure how long a person takes per chord and how often they hit a neighbouring chord; the prices in `CostParams`, `slip_prob` and `confusion_s` are still placeholders. Open `docs/index.html` from disk, or serve the `docs/` folder with GitHub Pages. The page has no build step, no npm and no external links; the interface is in Russian.

Rebuild `docs/data.js` (it is committed, because GitHub Pages needs it and the corpus is not in git):

```
uv run steno-zero rival --part train --out runs/rival-train.json
uv run steno-zero trainer export --table rival=runs/rival-train.json \
    --table evolved=runs/long-g1000-full-confusion-k6/best.json
```

The first table is the one opened by default; `index.html?table=evolved` picks another. `export` takes 200 home phrases from the train part of the corpus and 100 exam phrases from the test part (the two sets do not intersect), cuts each phrase with the same greedy segmentation as the simulator and writes everything, layout included, to one file. Running it again gives the same bytes. Options: `--corpus`, `--min-len`, `--max-len`, `--home-limit`, `--exam-limit`, `--exam-size`, `--out`.

The layout (finger to key) comes from the chosen setup, see "Fingers and layouts". The page shows two hands drawn in SVG, with the finger name and the key letter on each fingertip, and lights the tips in real time: yellow with a dashed outline for a finger that is needed but not held, green with a solid outline for a needed finger that is held, red with a solid outline and a cross for an extra finger. Where the page shows no goal (the exam, the home without a hint) a held finger is simply green: only the fact of the press. The exam therefore shows nothing that is a hint.

The help key is the physical `/` key (`Slash`, `.` on a Russian layout).

A chord fires when all its keys are released: press the keys together, let go, and the chord is the set of keys held since the first press. Since the hands show the fingers live, a wrong or missing finger **can be fixed before release**: let go of the red finger, press the yellow one, and the chord is still counted as a hit. A wrong chord is not accepted and the piece must be repeated (strict mode); there is no backspace.

Two modes. Home: phrase after phrase, help on the `/` key, a hint for the next piece, nothing is recorded. Exam (the "Экзамен" button): 5 random phrases from the exam set, no help and no hint, a timer that starts at the first key press. **Measurements are written only in the exam.** At the end the page shows the time, symbols per minute and misses, and "Скачать журнал" saves a JSON log (`steno-zero-<session>.json`, format `steno-zero/trainer-log`, version 2: session, table and its SHA-256, start and finish, user agent, the layout, the largest number of keys held at once, phrase indices and one record `phrase, pos, target, typed, down_ms, up_ms` per fired chord). An aborted exam leaves nothing.

```
uv run steno-zero trainer stats runs/trainer/*.json --out runs/trainer/stats.json
```

`trainer stats` prints one JSON line per session (time, symbols per minute, misses) and a summary line (misses by a neighbouring chord or otherwise, `slip_prob`, the median interval between clean consecutive chords). With `--out` the file also holds the time and the misses of every chord. `slip_prob` is the neighbour misses divided by the number of neighbours of all targets, the same quantity as `PenaltyParams.slip_prob`. These numbers are measurements of one person on one keyboard: a keyboard may lose keys pressed together (the page shows the largest number held at once; the three keyboards checked pass at most 6, hence the default `K = 6`), and the figures are not a general property of chords.

### Calibration and random chords

The exam measures only the 41-159 chords of one table, but a price model has to cover every chord the keyboard can type. So the page has two more modes, both written to separate logs.

**Keyboard facts.** The laptop passes at most 6 keys held together, and its matrix has no diodes, so some triples are swallowed: with `KeyF` and `KeyV` held, `KeyK` (also `KeyL`, `Semicolon`) never reaches the kernel, while `KeyF`, `KeyV` and `KeyJ` pass. A keyboard on Vial sees all 10 keys in the matrix but hands the browser at most 6 (a 6KRO report). A swallowed key looks in a log exactly like a human slip (the same chord without one key), so the keyboard is calibrated once before any measurement. While calibrating, a finger that stays yellow with its key held is a key the keyboard swallowed.

**Calibration** ("Калибровка клавиатуры"): the 45 pairs and 120 triples, each up to three attempts (about 5-6 minutes), and the page saves a `steno-zero/keyboard-calibration` log. Then

```
uv run steno-zero keyboard profile calibration.json --name laptop-vm   # writes data/keyboards/laptop-vm.json
```

builds a **keyboard profile**, the list of unavailable combinations of physical keys (`keyboard-profile` version 2 stores `KeyboardEvent.code` values, not fingers: a swallowed combination is a fact about the keys, whatever fingers they carry). A combination that never passed is blocked; only minimal blocked combinations are kept (a triple holding a blocked pair is not listed), and `unclear` marks one where an extra key arrived at least once (it may be a human slip, but it is excluded anyway; calibrate again and compare). A matrix without diodes blocks three keys in three corners of a rectangle, so a chord is unavailable exactly when it holds a blocked pair or triple; this is an assumption about the firmware, not a checked fact, and `price fit` lists suspicious chords as a safety net. The profile file is committed (`data/keyboards/`, no user agent in it) and is read by `read_profile`, which accepts blocked combinations of any length >= 2, so a suspicious chord can be added by hand. `--max-keys` only changes the `available` number of the summary (counted for the layout of the log).

Blocked fingers are derived from the profile through a layout. If the fingers are moved onto keys the profile already covers, no new calibration is needed; if a finger moves to a new key, only that needs a new calibration, and `trainer setups` and `price fit` say `not calibrated:` with the keys. The committed profile `data/keyboards/laptop-vn.json` is the first laptop calibration translated from the old layout (right thumb on `KeyN`): it does not cover `qwerty-vm` (no `KeyM`), so there is no setup with it, but what it knows about `KeyA`, `KeyS`, `KeyD`, `KeyF`, `KeyV`, `KeyJ`, `KeyK`, `KeyL` and `Semicolon` stays available to a layout that moves the thumb. `qwerty-vm` needs a new calibration.

**Random chords** ("Случайные аккорды"): the page shows a chord on a ten-key scheme with its label, you press it, and the page writes the time and the miss. A miss is not repeated: the wrong chord flashes red and the next one comes at once. The sequence is built in Python and played by the page, so all checked logic stays out of JS:

```
uv run steno-zero trainer drill      # writes docs/drill.js
uv run steno-zero trainer setups     # writes docs/setups.js
```

`docs/drill.js` holds 100 blocks of 100 chords over all chords of up to `--max-keys 6` fingers (seed 0) and the calibration queue, and is rebuilt byte for byte from these parameters. It is the plan of a setup without a keyboard profile; the page then warns that chords swallowed by the keyboard will give false misses. A setup with a keyboard profile has its own plan in `docs/setups.js`: the same algorithm over the chords the profile does not block, so blocks stay full and balanced and the page skips nothing. After a calibration or after `trainer drill` with other parameters, rebuild `setups.js` with `trainer setups`. The sampling is deliberately not uniform over chords: every block is balanced by the number of keys, then by the number of keys on the left hand, and inside a stratum chords come from a shuffled deck, so one-handed chords with many keys are measured too (small strata repeat often by design). No chord repeats in a row. `index.html?block=N` replays block `N`; otherwise a block is random.

A block log has the format `steno-zero/drill-log`, version 2: session `drill-<block>-<start>`, seed, block, `max_keys`, the layout, the keyboard (`name`, `sha256`, or `null`), start and finish, user agent, the largest number of keys held and one record `i, target, typed, shown_ms, down_ms, up_ms` per chord (`i` is the index in the plan of the setup, `keyboard` and `seed` tell which plan) (`performance.now()` times; `shown_ms` is taken when the scheme is already in the page).

The hands light the target live in this mode too, so the times and the misses of random chords and of calibration were taken with that feedback: a corrected chord is a hit, and its time includes the correction. The exam shows no goal and is not affected. Whether the live highlight slows the pace (eyes go to the hands instead of the label) is to be noted from the first live blocks.

Old version 1 files (right thumb on `KeyN`, keys named by letters) are not read: `trainer-log` version 2, `drill-log` version 2, keyboard profile version 2 and calibration version 2 all carry the layout or physical codes. The one random-chord block taken that way was a trial.

## Chord prices

```
uv run steno-zero price fit runs/drill/*.json --keyboard data/keyboards/laptop-vm.json --out runs/price
uv run steno-zero price fit runs/drill/*.json --layout qwerty-vm --out runs/price   # only the logs of one layout
```

`price fit` reads the logs of random chords into a pandas table (one row per presentation, the first 5 of each session dropped as warm-up) and writes `prices.json` and `report.json`. Features of a chord (19): `fingers` (how many), fingers per hand, both hands, one flag per finger (`L4` .. `R4`), `thumb_index` (the pairs `L1 L0` and `R0 R1`), adjacent pressed fingers, the span and the holes per hand, and a mirrored left/right shape. The thumb is its own finger here (the old table put the thumbs with the index fingers). The target is `total` (release minus display) or `motor` (release minus first press); a miss is not a time, and slower rows than `--max-ms` are dropped.

The baseline (the mean time by the number of keys), Ridge and gradient boosting are compared by 5-fold `GroupKFold` **by chord**, so every score is for chords the model has not seen. Metrics: MAE, R2 and the mean per-chord error. The miss probability is compared in the same way (a smoothed rate by the number of keys against logistic regression, log loss and Brier score). `auto` picks the model with the smallest MAE. `prices.json` gives a time and a miss probability for **all** chords allowed by `--max-keys`: availability on a keyboard is a property of a setup, not of fingers, and the estimate for chords not seen is exactly what `GroupKFold` checks. `report.json` also has the Ridge coefficients, per-session medians (drift) and `suspect_chords`: chords whose presentations all missed, each time with a strict subset of the keys, which may be a key the keyboard swallows and is not in the profile.

Logs of different layouts are read together, because the model is about fingers and a layout only imitates the hand; if there is more than one layout `price fit` prints `warning: mixing drill logs of N layouts: NAME (K sessions), ...` to stderr and `report.json` has the split `layouts`. `--layout NAME` keeps the logs of one layout. Two layouts with one name and different codes are an error. Logs taken on different profiles (or some with and some without) are never mixed, and the profile given to `--keyboard` must be the one recorded in the logs. The human slip and a swallowed key cannot be told apart from a log alone, which is why the profile exists. On synthetic data with a known dependence Ridge recovers it and beats the baseline several times over (the tests check it); **there are no numbers from live measurements yet**, and the prices are not connected to the evolution. The time of a random chord includes recognising the scheme, which fluent typing does not have, so it is not yet an absolute price.

## Not supported

- Crossover of tables and resuming an interrupted run.
- Online retraining of the surrogate during evolution.
- Surrogate models across corpora or cost parameters.
- Chord prices that depend on the previous chord, slips of more than one key, per-finger slip rates, measured slip rates, measured prices (the `price fit` model exists, but there are no live measurements and nothing feeds them to the evolution), calibration of drill times to fluent typing.
- Memory penalty stages beyond a per-entry cost with a rarity surcharge.
- Free typing with backspace in the trainer, an estimate of `confusion_s` and measurements in the home mode.
- Merging calibrations of different key sets into one keyboard profile, and a layout feature in the price model (one or two layouts over dozens of chords would only overfit).
- Key-blocking check beyond pairs and triples, and an evolution that avoids chords blocked by a keyboard profile.
- Capital letters, digits, quotes, brackets, Latin letters and line breaks: normalisation drops them.

## License

Apache-2.0, see `LICENSE`. The corpus texts are in the public domain.

# steno-zero

A test bench for one question: which table "piece of text -> chord" on ten keys would evolution find, with no ready-made human system to start from? This repository is the bench: a Russian corpus, a typing simulator that scores a table by `T = H * t_char + M`, and a frequency-based rival that any evolved table has to beat. Evolution itself is not here yet.

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

## Not supported

- Evolution of tables, the neural network, plots and run logs.
- Chord prices that depend on the previous chord, key press errors, measured prices.
- Memory penalty stages beyond a per-entry cost with a rarity surcharge.
- Capital letters, digits, quotes, brackets, Latin letters and line breaks: normalisation drops them.

## License

Apache-2.0, see `LICENSE`. The corpus texts are in the public domain.

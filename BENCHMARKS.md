# Benchmarks

Every number here was produced by running the code. Nothing is estimated.

Reproduce with:

```bash
python -m termchess.bench                          # table
python -m termchess.bench --compare baseline.json  # diff against the baseline
python chess_game.py --benchmark                   # same, via the game
```

## Method

The benchmark searches a fixed set of positions to a **fixed depth**, not for a
fixed time. A time-limited search visits a different number of nodes on every
machine and every run, so it cannot detect a regression. At fixed depth the node
count is deterministic and therefore a real before/after signal.

- **Node counts are authoritative.** They are reproducible on any machine.
- **Wall-clock and NPS are indicative only.** They depend on the host.
- `blunder=0` and an effectively infinite time limit keep move choice deterministic.

One caveat that applies to every number below: `nodes` counts entries to
`negamax`/`quiesce` only. `legal_moves()` performs a full make/unmake per
pseudo-legal move without counting, so the real work done is undercounted. These
figures are comparable to each other, **not** to other engines.

## Baseline — pre-improvement (branch `engine-improvements`, 2026-08-17)

Python 3.13.14, Windows 11. Saved as `baseline.json`.

| position | depth | nodes | qnodes | cutoffs | nps | ebf | time | score | best |
|---|---|---|---|---|---|---|---|---|---|
| startpos | 5 | 81,084 | 41,021 | 36,400 | 67,435 | 12.30 | 1.20s | +0.40 | Nc3 |
| italian | 5 | 474,062 | 293,040 | 249,200 | 54,184 | 8.46 | 8.75s | +0.15 | O-O |
| kiwipete | 4 | 48,805 | 39,049 | 34,873 | 37,972 | 4.30 | 1.29s | +0.95 | Bxa6 |
| promotion | 4 | 11,503 | 8,972 | 7,636 | 41,722 | 2.18 | 0.28s | -3.75 | c5 |
| endgame | 6 | 154,538 | 83,858 | 68,233 | 56,782 | 5.73 | 2.72s | -0.01 | Rxf4+ |
| **TOTAL** | | **769,992** | **465,940** | **396,342** | **54,095** | | **14.23s** | | |

**Quiescence is 60.5% of all nodes** (80% in kiwipete). Transposition table: not
implemented yet.

### Deeper reference points

| Position | Depth | Nodes | Time | NPS |
|---|---|---|---|---|
| startpos | 4 | 7,579 | 0.16s | 48.3k |
| startpos | 5 | 81,084 | 1.21s | 67.3k |
| startpos | 6 | 450,836 | 9.25s | 48.7k |
| kiwipete | 5 | 295,758 | 6.17s | 48.0k |

Move generation alone: perft(3) = 8,902 in 0.05s ~ 191k nps.

### Where the time goes

cProfile of a depth-5 search from the starting position (2.56s total, by `tottime`):

| Hot spot | tottime | Calls | Note |
|---|---|---|---|
| `evaluate()` | 0.766s (41% cum) | 41,021 | scans 64 squares twice, allocates 3 lists per call |
| `gen_pseudo()` | 0.373s (23% cum) | 14,719 | |
| `attacked()` | 0.321s (14% cum) | 119,506 | |
| `str.upper()` + `str.isupper()` | 0.386s (15%) | 4,359,889 | representation tax |
| `has_mating_material()` | 0.081s | 40,063 | runs at every node |
| `list.index` (`king_sq`) | 0.042s | 104,768 | linear scan |

Two independent axes follow from this, and they are tracked separately because
mixing them makes it impossible to tell which change paid:

- **Nodes/sec** -- representation and evaluation cost.
- **Nodes-to-depth** -- move ordering and transposition table. The measured EBF
  of 12.30 (startpos, d4->d5) is high; good ordering should pull it down sharply.

## Test baseline

| Suite | Result |
|---|---|
| `pytest -q -m "not slow"` | 271 passed, 1 deselected, 6.32s |
| `pytest -q` (full, incl. perft depth 5) | 272 passed, 28.95s |

perft(5) from the starting position = 4,865,609 -- this must never regress.

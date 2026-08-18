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

## Phase 2 -- representation and evaluation performance

Same tree, explored faster. Node counts are **identical** to the baseline in
every position (+0.0%), and every best move is unchanged, so the entire
difference is throughput rather than a changed search. Saved as
`bench-phase2.json`.

| position | depth | nodes | nps (baseline) | nps (now) | speed |
|---|---|---|---|---|---|
| startpos | 5 | 81,084 | 67,435 | 134,217 | **+99.0%** |
| italian | 5 | 474,062 | 54,184 | 108,580 | **+100.4%** |
| kiwipete | 4 | 48,805 | 37,972 | 74,334 | **+95.8%** |
| promotion | 4 | 11,503 | 41,722 | 82,229 | **+97.1%** |
| endgame | 6 | 154,538 | 56,782 | 122,763 | **+116.2%** |
| **TOTAL** | | **769,992** | **54,095** | **109,601** | **2.03x** |

Benchmark suite wall-clock: 14.23s -> 7.03s. Full test suite: 28.95s -> 17.06s.

### What changed, and what it bought

| Change | Effect |
|---|---|
| Precomputed knight/king target lists, rays, pawn-attacker tables | `attacked()` 0.321s -> 0.107s |
| Combined material+PST+sign tables keyed by raw piece char | `evaluate()` 0.766s -> 0.224s |
| Incremental `heavy` material, so evaluation stops rescanning for the endgame test | removed a whole 64-square pass per evaluation |
| Incremental `prq`/`npieces` | `has_mating_material()` went from a list allocation per node to two integer comparisons |
| Incremental king squares | removed 104,768 `list.index` scans |
| `CHAR_VALUE` in MVV-LVA ordering, char-keyed piece sets in movegen | eliminated **all** 4.36M `.upper()`/`.isupper()` calls |
| Copy-on-write castling rights | removed a set allocation from most of ~145,000 `make()` calls |

Profile of the same depth-5 search, before and after: **2.560s -> 1.006s**, with
total function calls falling from 6,616,805 to 1,790,169. `str.upper` and
`str.isupper` no longer appear in the profile at all.

Remaining hot spots, for reference:

| Hot spot | tottime | Note |
|---|---|---|
| `evaluate()` | 0.224s | still the largest single cost |
| `pseudo_moves()` | 0.171s | |
| `make()` | 0.121s | 144,831 calls, mostly from the legality filter |
| `attacked()` | 0.107s | |

The next large win is not in these functions individually but in `legal_moves()`
calling make/unmake once per pseudo-legal move to test legality. Replacing that
with pin detection is a correctness-sensitive redesign, so it is deliberately
not attempted here.

## Phase 3 -- Zobrist hashing and transposition table

The other axis: fewer nodes to reach the same depth. Saved as
`bench-phase3.json`. Compared against the original baseline:

| position | depth | nodes (base) | nodes (now) | nodes | ebf (base) | ebf (now) | speed |
|---|---|---|---|---|---|---|---|
| startpos | 5 | 81,084 | 35,745 | **-55.9%** | 12.30 | 11.05 | +85.9% |
| italian | 5 | 474,062 | 178,147 | **-62.4%** | 8.46 | 4.75 | +85.6% |
| kiwipete | 4 | 48,805 | 41,089 | **-15.8%** | 4.30 | 3.57 | +82.5% |
| promotion | 4 | 11,503 | 10,189 | **-11.4%** | 2.18 | 1.76 | +98.4% |
| endgame | 6 | 154,538 | 56,329 | **-63.6%** | 5.73 | 6.60 | +89.4% |
| **TOTAL** | | **769,992** | **321,499** | **-58.2%** | | | |

Best move unchanged in every position. Transposition table hit rate: **10.7%**.

**Cumulative: benchmark wall-clock 14.23s -> 3.30s, a 4.31x speedup.**

### Measured step by step

Each change was benchmarked on its own, which is the only way to know what
actually paid:

| Step | Nodes | Speed | Note |
|---|---|---|---|
| Zobrist hash, maintained incrementally | +0.0% | -4% to -9% | pure overhead until something uses it |
| Fail-hard -> fail-soft | **+0.0%** | ~0% | see below |
| Transposition table | **-58.3%** | -12% NPS, but wall-clock 7.03s -> 3.56s | |
| Repetition detection in search | +0.06% | ~0% | correctness, not speed |

The fail-soft conversion changed **no node counts at all**, which is worth
explaining rather than just recording. When a child fails high it was searched
with window `(-beta_parent, -alpha_parent)`, so its return value is at least
`-alpha_parent`; negated at the parent that is at most `alpha_parent`. Fail-hard
returns exactly `alpha_parent`, fail-soft returns something less. Neither is
greater than alpha, so neither updates alpha and neither causes a cutoff -- the
pruning decisions are identical by construction. What changes is the *quality of
the information*: fail-soft returns a real bound instead of a restated window
edge, which is precisely what makes a transposition entry worth storing.

NPS falls from 109,601 to 97,519 because hashing and table probing are real work
per node. That is the right trade: the search visits 58% fewer nodes, so total
time still drops by more than half.

## Phase 4 (in progress) -- delta pruning in quiescence

Quiescence was 61.7% of all nodes, so it was the largest remaining target.
Delta pruning skips a capture when even winning the victim outright, plus a
200cp margin, cannot reach alpha. Disabled below 1300cp of non-pawn material,
where a single pawn can decide the game and the assumption stops holding.

| position | nodes (phase 3) | nodes (now) | change |
|---|---|---|---|
| startpos | 35,745 | 35,696 | -0.1% |
| italian | 178,147 | 167,797 | -5.8% |
| kiwipete | 41,089 | 24,632 | **-40.1%** |
| promotion | 10,189 | 7,509 | **-26.3%** |
| endgame | 56,329 | 56,280 | -0.1% |
| **TOTAL** | **321,499** | **291,914** | **-9.2%** |

Wall-clock 3.30s -> 2.99s. Quiescence share 61.7% -> 57.8%. Best move
unchanged in every position.

The gain is concentrated exactly where it should be: kiwipete and promotion are
the tactical positions full of captures that go nowhere. The quiet positions
(startpos, endgame) barely move, and the endgame is largely excluded by the
material floor by design.

**Cumulative so far: 769,992 -> 291,914 nodes (-62.1%), 14.23s -> 2.99s (4.76x).**

## Phase 5 -- evaluation quality

Evaluation now understands things it previously could not see, at a real cost
in speed. Saved as `bench-phase5.json`. The frozen values in
`tests/test_eval_regression.py` were regenerated in the same commit: **43 of 48
changed**, which is the evidence that the evaluation genuinely moved.

| position | nodes (phase 4a) | nodes (now) | nodes | speed |
|---|---|---|---|---|
| startpos | 35,696 | 35,010 | -1.9% | -33% |
| italian | 167,797 | 167,115 | -0.4% | -33% |
| kiwipete | 24,632 | 24,747 | +0.5% | -22% |
| promotion | 7,509 | 7,759 | +3.3% | -32% |
| endgame | 56,280 | 31,695 | **-43.7%** | -21% |
| **TOTAL** | **291,914** | **266,326** | **-8.8%** | |

Wall-clock 2.99s -> 3.90s (+30%); NPS 97,608 -> 68,330. Best move unchanged in
every position.

### The trade, stated plainly

This is the first phase that made the benchmark **slower**. The evaluation does
substantially more work per call, and evaluation is called once per quiescence
node -- 58% of all nodes. A 30% wall-clock cost is roughly a third of a ply of
search depth; understanding passed pawns, king safety and open files is worth
considerably more than that in playing strength. The endgame position is the
visible proof: **-43.7% nodes**, because an evaluation that actually understands
passed pawns guides the search instead of groping.

Should that judgement ever need revisiting, the levers are: fold the
middlegame/endgame pair into a single table of tuples (done -- recovered ~4%),
or cache pawn-structure results by pawn hash, which is the standard next step
and was not attempted here.

### What was added, and why each earns its place

| Term | Justification |
|---|---|
| Tapered midgame/endgame phase | The old code flipped the king table the instant material crossed 1300cp. A single capture could swing the score for no positional reason, and the search chased that discontinuity. |
| Endgame pawn table | In the endgame a pawn's only job is to promote, so advancement outweighs central shape. |
| Passed pawns (rank-scaled, endgame-weighted) | The single most important endgame feature; an unstoppable passer simply wins. |
| Doubled / isolated / backward pawns | Structural weaknesses that cannot be defended by other pawns. |
| Rook on open / semi-open file | A rook's value is mostly the file it stands on. |
| King pawn shield (middlegame only) | Only dangerous while pieces remain to exploit it -- the clearest illustration of why tapering exists. |
| Bishop pair | Covers both colour complexes; worth more than the sum of its parts. |

**Mobility was considered and rejected.** It requires generating moves inside
the evaluation, which runs once per quiescence node. The cost is far larger than
the terms above and the benefit largely overlaps the piece-square tables, which
already reward pieces on squares from which they have scope.

**Cumulative: 769,992 -> 266,326 nodes (-65.4%), 14.23s -> 3.90s (3.65x).**

## Phase 4 (complete) -- search improvements

Null-move pruning, late move reductions, mate-distance pruning, killer moves,
the history heuristic, and principal-variation extraction. Saved as
`bench-phase4b.json`.

| position | depth | nodes (phase 5) | nodes (now) | ebf before | ebf now |
|---|---|---|---|---|---|
| startpos | 5 | 266,326 total | 7,372 | 12.30 | **4.85** |
| italian | 5 | | 31,220 | 8.46 | **2.62** |
| kiwipete | 4 | | 22,374 | 4.30 | 2.05 |
| promotion | 4 | | 5,696 | 2.18 | 1.40 |
| endgame | 6 | | 15,698 | 5.73 | 4.12 |
| **TOTAL** | | **266,326** | **82,360** | | |

Transposition hit rate rose to **18.4%**, because better ordering means more
positions are reached by their best move first.

**Cumulative: 769,992 -> 82,360 nodes (-89.3%), 14.23s -> 1.56s (9.12x).**

### Difficulty levels, measured rather than advertised

`depth` is a ceiling; iterative deepening stops at whichever of depth-or-clock
comes first, and in a sharp position the clock wins. The old settings claimed
depth 8 for Brutal while never exceeding 6, so Brutal and Hard were the same
opponent. Measured depths actually reached with the current engine:

| level | depth cap | time | startpos | kiwipete |
|---|---|---|---|---|
| Easy | 3 | 0.5s | 3 | 3 |
| Medium | 6 | 2.0s | 6 | 5 |
| Hard | 8 | 6.0s | 7 | 5 |
| Brutal | 12 | 15.0s | 8 | 5 |

In quiet positions the levels now separate cleanly. In a dense tactical
position such as kiwipete the top two still converge at depth 5 -- the branching
factor there is simply too high for another ply inside the budget. That is an
honest limit of the engine rather than something the labels should hide.

## Final -- Phases 6 to 8

Saved as `bench-final.json`. Compared against the original baseline:

| position | depth | nodes (base) | nodes (final) | change | ebf (base) | ebf (final) |
|---|---|---|---|---|---|---|
| startpos | 5 | 81,084 | 7,372 | **-90.9%** | 12.30 | **4.85** |
| italian | 5 | 474,062 | 31,220 | **-93.4%** | 8.46 | **2.62** |
| kiwipete | 4 | 48,805 | 22,374 | -54.2% | 4.30 | 2.05 |
| promotion | 4 | 11,503 | 5,696 | -50.5% | 2.18 | 1.40 |
| endgame | 6 | 154,538 | 15,698 | **-89.8%** | 5.73 | 4.12 |
| **TOTAL** | | **769,992** | **82,360** | **-89.3%** | | |

**Wall-clock 14.23s -> 1.50s: 9.50x faster.** Transposition hit rate 18.4%.
Quiescence is 61.5% of remaining nodes.

### Quality gates

| Gate | Result |
|---|---|
| `pytest -q -m "not slow"` | 500 passed, 23 deselected, 47.7s |
| `pytest -q` (full, incl. perft depth 5) | **523 passed**, 380s |
| `ruff check .` | clean |
| `mypy` | clean, 12 source files |
| Coverage of `termchess/` | **92%** |

perft(5) from the starting position = 4,865,609, unchanged throughout.

# terminal-chess

A complete chess game and chess engine in pure Python, with no dependencies at
all. Clone it and run it:

```bash
python chess_game.py
```

That is the entire install procedure. The engine, the rules, the notation
parser and the interface are standard library only — there is nothing to
`pip install`, nothing to build, and nothing to configure.

```
   +------------------------+
 8 | ♜  ♞  ♝  ♛  ♚  ♝  ♞  ♜ |
 7 | ♟  ♟  ♟  ♟  .  ♟  ♟  ♟ |
 6 |    .     .     .     . |
 5 | .     .     ♟     .    |
 4 |    .     .  ♙  .     . |
 3 | .     .     .     ♘    |
 2 | ♙  ♙  ♙  ♙     ♙  ♙  ♙ |
 1 | ♖  ♘  ♗  ♕  ♔  ♗     ♖ |
   +------------------------+
     a  b  c  d  e  f  g  h
  2. > Nc6
  You play Nc6
  Thinking...  Computer plays Bb5     (depth 8, +0.15, 1.4s, 31220 nodes)
  expecting: Bb5 a6 Ba4 Nf6 O-O
```

## What makes it interesting

It is not just a rules implementation. The engine is a real alpha-beta searcher
with the machinery that implies, and every claim below is backed by a
reproducible measurement in [BENCHMARKS.md](BENCHMARKS.md):

- **Iterative-deepening negamax** with fail-soft alpha-beta
- **Transposition table** with Zobrist hashing, depth-preferred replacement and
  ply-corrected mate scores
- **Null-move pruning**, **late move reductions** and **mate-distance pruning**
- **Quiescence search** with delta pruning, so evaluation never lands mid-trade
- **Move ordering** by transposition move, MVV-LVA captures, killers, then a
  history heuristic
- **Tapered evaluation** sliding between middlegame and endgame readings, with
  passed pawns, pawn-structure weaknesses, rook files and king safety
- **Repetition detection inside the search**, so the engine can see a perpetual
- **Perft-verified move generation** against published counts to depth 5

## Performance

Measured on the benchmark suite (five fixed positions at fixed depth), against
the engine as it stood before this work:

| | Before | Now | |
|---|---|---|---|
| Nodes to reach the same depths | 769,992 | **82,360** | −89.3% |
| Wall-clock | 14.23s | **1.50s** | **9.50× faster** |
| Effective branching factor (start position) | 12.30 | **4.85** | |
| Transposition hit rate | — | 18.4% | |

Node counts are the authoritative figure: they are deterministic and reproduce
on any machine. Wall-clock depends on the host.

Reproduce it yourself:

```bash
python -m termchess.bench                          # the table
python -m termchess.bench --compare baseline.json  # diff against the original
python chess_game.py --benchmark                   # same, through the game
```

## Playing

Moves are accepted in either notation:

```
e2e4    g1f3    e7e8q          coordinates, with an optional promotion piece
e4      Nf3     exd5   O-O     standard algebraic notation
```

### Commands

| | |
|---|---|
| `board` `flip` `moves` `fen` | look at the position |
| `setfen <FEN>` `history` `new` `undo` | change or review the game |
| `eval` | static evaluation, with no search at all |
| `analyze [FEN]` | full search report: verdict, best move, PV, statistics |
| `hint` | the move the engine would play here |
| `go` | let the engine move for you |
| `perft <n>` | count leaf nodes at depth n |
| `depth <n>` `time <secs>` | change how hard the engine thinks |
| `save <file>` `load <file>` | write or read a PGN file |

### Difficulty

`depth` is a ceiling, not a promise — iterative deepening stops at whichever of
depth-or-clock comes first, and in a sharp position the clock usually wins.
These are the depths actually reached, measured rather than advertised:

| Level | Depth cap | Time | Reached (quiet) | Reached (tactical) |
|---|---|---|---|---|
| Easy | 3 | 0.5s | 3 | 3 |
| Medium | 6 | 2.0s | 6 | 5 |
| Hard | 8 | 6.0s | 7 | 5 |
| Brutal | 12 | 15.0s | 8 | 5 |

Easy and Medium also blunder on purpose, choosing at random among moves within
a centipawn margin of the best, so they lose plausibly rather than randomly.

## As an analysis tool

Any position can be analysed without playing a game:

```bash
python chess_game.py --analyze "6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1"
```

```
  position   6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1
  static     +5.25  (evaluation before any search)
  verdict    mate in 1 for White
  best move  Ra8#
  pv         Ra8#

  depth      2 of 8 requested
  nodes      124  (56 in quiescence, 45%)
  time       0.00s at 110419 nodes/sec
  cutoffs    39
  table      12 entries, 0 of 13 probes hit (0.0%)
```

The same report is available in-game with `analyze`, which also accepts a FEN.

## Architecture

```
chess_game.py          entry point; re-exports the public API
termchess/
  constants.py         board geometry and precomputed tables; imports nothing
  board.py             position state, make/unmake, FEN, Zobrist hashing
  movegen.py           pseudo-legal generation, attack detection, legality
  evaluate.py          tapered evaluation
  search.py            negamax, alpha-beta, quiescence, transposition table
  notation.py          SAN generation and parsing
  pgn.py               game import and export
  analyze.py           position analysis reporting
  perft.py             move-generation verification
  cli.py               rendering and the interactive loop
  bench.py             the benchmark harness
```

Each module imports only from those above it, so the dependency graph is
acyclic. The package is named `termchess` rather than `chess` deliberately: a
top-level `chess` package would shadow the widely-installed `python-chess` for
anyone who has it.

### How the search works

Alpha-beta only prunes well if the best move is tried early, so most of the
engine's speed comes from ordering rather than from raw evaluation throughput:

1. The **transposition table's** move — a real result from a real search
2. **Captures**, richest victim by cheapest attacker
3. **Promotions**
4. **Killers** — quiet moves that refuted a sibling line at this ply
5. Everything else, by **history** — how often it has caused a cutoff before

On top of that, **null-move pruning** asks whether the position is so good that
the opponent cannot catch up even if we simply pass; **late move reductions**
search unpromising moves one ply shallower and re-search only if they surprise
us; and **delta pruning** discards captures in quiescence that cannot reach
alpha even in the best case.

### How the evaluation works

A position is not simply middlegame or endgame — it slides between them as
pieces come off. Every position gets a phase from 24 down to 0, and the score
interpolates between two readings. Terms that belong to one regime are weighted
into that reading: king safety is middlegame-only, passed pawns count for far
more in the endgame.

Every term is colour-symmetric by construction, and a test asserts that a
position and its mirror image score as exact negatives.

## Testing

```bash
python -m pytest -q -m "not slow"   # fast gate
python -m pytest -q                 # everything, including perft to depth 5
python -m ruff check .              # lint
python -m mypy                      # types
```

**500 tests** in the fast gate, 523 in total, at **92% coverage** of the
package. The suite is built around properties rather than examples where it
can be:

- **Perft** against published counts for five standard positions — the
  authority on move generation being correct
- **Make/unmake integrity** — every field restored, three plies deep, plus a
  seeded 120-move game unwound in reverse
- **Zobrist consistency** — the incremental hash must always equal the
  from-scratch hash
- **Evaluation symmetry** — mirrored positions score as exact negatives
- **Frozen evaluation values** — 48 positions locked, regenerated only in the
  same commit that deliberately changes the evaluation
- **Tactical suite** — mates, material wins and blunders to avoid, each
  verified against the engine before being written down
- **PGN round-tripping** — export, parse, export must converge

## Development

```bash
git clone https://github.com/raamputtagunta045-cmyk/terminal-chess.git
cd terminal-chess
pip install -r requirements-dev.txt
python -m pytest -q -m "not slow"
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the rules that matter — chiefly that
perft must never regress and benchmark numbers must never be estimated.

## Roadmap

The most promising remaining work, roughly in order of expected value:

1. **Faster legality filtering.** `legal_moves()` plays and unplays every
   pseudo-legal move to test it. Pin detection would avoid most of that, and it
   is the single largest remaining cost in the profile.
2. **A pawn-structure cache** keyed by a pawn-only hash. Evaluation runs once
   per quiescence node and recomputes the same pawn analysis constantly.
3. **Aspiration windows** around the previous iteration's score.
4. **Opening book and endgame tablebase probing**, which would improve play at
   both ends of the game far more cheaply than more search.

A known limitation: repetition draws are path-dependent, but their consequences
are cached in a transposition table keyed only on position. This is standard
practice and no misplay has been demonstrated, but it is a real theoretical
hole.

## Licence

MIT. See [LICENSE](LICENSE).

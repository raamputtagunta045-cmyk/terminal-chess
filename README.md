# Terminal Chess

A complete chess game with a built-in engine, in a single Python file. No dependencies —
just the standard library.

```
   +------------------------+
 8 | r  n  b  q  k  b     r |
 7 | p  p  p  p  p  p  p  p |
 6 |    .     .     n     . |
 5 | .     .     .     .    |
 4 |    .     .  P  .     . |
 3 | .     .     .     .    |
 2 | P  P  P  P     P  P  P |
 1 | R  N  B  Q  K  B  N  R |
   +------------------------+
     a  b  c  d  e  f  g  h

  1. > e4
  You play e4
  Computer plays Nf6      (depth 4, +0.35, 0.3s, 19416 nodes)
```

(In a real terminal the pieces render as `♜♞♝♛♚♟`; it falls back to letters when the
console can't encode them.)

## Features

- **Complete rules.** Castling, en passant, promotion, pinned pieces, checkmate,
  stalemate, the fifty-move rule, threefold repetition, and insufficient material.
- **Real engine.** Iterative-deepening negamax with alpha-beta pruning, quiescence search,
  MVV-LVA move ordering, and piece-square-table evaluation.
- **Both notations.** Type `e2e4` or `Nf3` — coordinate and algebraic both work.
- **Verified correctness.** 191 tests, including [perft][perft] to depth 5 (4,865,609
  positions) and four standard reference positions.

[perft]: https://www.chessprogramming.org/Perft

## Requirements

Python 3.8 or newer. Nothing else.

## Play

```bash
git clone https://github.com/raamputtagunta045-cmyk/terminal-chess.git
cd terminal-chess
python chess_game.py
```

You'll be asked which colour you want and how strong the engine should be, then it's your
move.

## Entering moves

Either notation works:

| Style | Examples |
|---|---|
| Coordinate | `e2e4`, `g1f3`, `e7e8q` |
| Algebraic | `e4`, `Nf3`, `exd5`, `O-O`, `e8=Q` |

Bare coordinates promote to a queen by default; add `q`, `r`, `b`, or `n` to choose.
Check and mate suffixes (`+`, `#`) are optional.

## Commands

| Command | Effect |
|---|---|
| `moves` | List every legal move |
| `undo` | Take back your move and the reply |
| `board` | Redraw the position |
| `flip` | Flip board orientation |
| `fen` | Print the position as FEN |
| `new` | Restart |
| `help` | Show help |
| `quit` | Exit |

## Difficulty

| Level | Depth | Time budget | Behaviour |
|---|---|---|---|
| Easy | 2 | 0.4s | Picks randomly within 90cp of best — makes real mistakes |
| Medium | 4 | 1.5s | Within 25cp of best — occasionally loose |
| Hard | 6 | 4.0s | Always plays its best move |
| Brutal | 8 | 10.0s | Always best, searches deepest |

Easy and Medium are deliberately imperfect. The randomness is bounded by a centipawn
threshold rather than being uniformly random, so they play plausible moves and blunder
like a human rather than flailing.

## How it works

The board is a flat 64-element list, index 0 being a8 and 63 being h1 — rank 8 first, so
it lines up with FEN. Uppercase is White, lowercase Black.

Move generation produces pseudo-legal moves, then filters them by playing each one and
testing whether the mover's king is attacked. Attack detection works *backwards* from the
target square — casting rays outward and checking what sits at the end — instead of
enumerating every enemy move, which keeps it cheap enough to call inside search.

The search is negamax with alpha-beta, extended by a capture-only quiescence search so the
engine doesn't stop evaluating in the middle of a trade. Iterative deepening means it always
has a usable move ready when the clock runs out. Evaluation is material plus piece-square
tables, with bonuses for the bishop pair and penalties for doubled and isolated pawns, and
a separate king table for the endgame.

`make()` returns an undo record that `unmake()` consumes, so the search never copies the
board.

## Tests

```bash
pip install -r requirements-dev.txt

python -m pytest -q                  # everything (~25s)
python -m pytest -q -m "not slow"    # skip perft(5) (~4s)
python -m pytest -q -k castling      # one topic
```

Coverage:

```bash
python -m coverage run -m pytest -q -m "not slow"
python -m coverage report --show-missing --include=chess_game.py
```

The suite covers move generation, castling rights and transit-square rules, en passant
(including the case where capturing would expose the king), promotion, absolute pins,
game-end detection, `make`/`unmake` symmetry, SAN round-tripping, evaluation symmetry, and
search behaviour.

Perft is the real guarantee. Unit tests alone won't catch move-generation bugs, so any
change to `gen_pseudo()` or `legal_moves()` has to keep `TestPerft` green.

## Layout

```
chess_game.py        the game and engine
test_chess_game.py   191 tests
pytest.ini           registers the "slow" marker
```

## Licence

MIT — see [LICENSE](LICENSE).

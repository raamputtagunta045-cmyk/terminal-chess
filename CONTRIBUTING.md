# Contributing

Thanks for taking a look. The project is small and the rules that matter are
few, but they are strict, because a chess engine fails in ways that are easy to
miss: nothing crashes, the moves stay legal, and the engine just plays slightly
worse than it did yesterday.

## The three rules

**1. Perft must never regress.**

```bash
python -m pytest -q            # includes perft to depth 5
```

Move generation is verified against published node counts for five standard
positions. If those numbers change, move generation is wrong — no matter how
reasonable the change looked. This is not negotiable, and no amount of passing
unit tests substitutes for it.

**2. Never report a number you did not measure.**

Every figure in `BENCHMARKS.md` and `README.md` was produced by running the
code. If you change the engine, run the benchmark and paste what it printed:

```bash
python -m termchess.bench --compare bench-final.json
```

Node counts are the signal. They are deterministic, so a change in node count
means the search took a different path through the tree — which is either the
point of your change or a bug in it. Wall-clock is machine-dependent and worth
reporting only alongside node counts.

**3. Existing tests do not get weakened to make a change pass.**

If a test fails, either the change is wrong or the test encodes a belief that
is wrong. Both happen. Work out which before touching either — and if it is the
test, say so in the commit message and explain why.

This has already earned its place. During the evaluation rework,
`test_doubled_pawns_penalised` failed because an advanced doubled pawn was
collecting a passed-pawn bonus, making a doubled isolated pair score better
than two healthy connected pawns. The test was right; the new evaluation was
wrong.

## Changing the evaluation

`tests/test_eval_regression.py` freezes 48 evaluation values. Any deliberate
change to scoring will break it — that is what it is for.

**Regenerate those values in the same commit as the change**, never in a
follow-up, so the diff shows the code and the scores moving together. A value
that moves on its own means something shifted that nobody intended.

Every evaluation term must be colour-symmetric: a position and its mirror image
must score as exact negatives. `tests/test_eval_symmetry.py` enforces this, and
it is worth understanding why it is not optional. A term applied to one colour
and forgotten for the other does not crash anything; it just makes the engine
quietly prefer being White.

Note also what that suite *cannot* catch: a bug that is wrong in the same way
for both colours passes symmetry perfectly. One shipped exactly like that — a
passed-pawn test reading the wrong end of the enemy pawn file — and was found
by review, not by tests.

## Changing the search

Implement one thing at a time and benchmark each on its own. A combined
measurement cannot tell you which half paid, and search heuristics are quite
capable of cancelling each other out.

If a change is meant to be behaviour-preserving — a refactor, an optimisation —
then node counts must be **identical**, not merely similar. That is a far
stronger check than the tests passing, because it proves the search explored
exactly the same tree.

## Before opening a pull request

```bash
python -m pytest -q -m "not slow"   # fast gate
python -m pytest -q                 # full, including deep perft
python -m ruff check .
python -m mypy
python chess_game.py                # it must still actually play
```

CI runs all of these on Python 3.9, 3.11 and 3.13, plus a coverage floor and a
smoke test that plays a real move.

## Style

Match the surrounding code. A few things worth knowing:

- **No runtime dependencies.** The game is standard library only and stays that
  way. Development tools are a separate matter.
- **Comments explain why, not what.** The engine is full of decisions that look
  arbitrary until you know the reason — why the undo record stores the previous
  hash rather than recomputing it, why null-move pruning is disabled in
  endgames, why `_divide` truncates toward zero instead of using `//`. Those
  reasons belong next to the code.
- The hot paths are deliberately written for speed over elegance, and say so.
  Everywhere else, prefer clarity.

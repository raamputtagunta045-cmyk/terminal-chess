## What this changes

## Why

## Verification

Please paste actual output rather than ticking boxes from memory.

- [ ] `python -m pytest -q -m "not slow"`
- [ ] `python -m pytest -q` (full suite, including perft to depth 5)
- [ ] `python -m ruff check .`
- [ ] `python -m mypy`
- [ ] `python chess_game.py` still plays a game

### If this touches move generation

Perft must be unchanged. Paste the result:

```
```

### If this touches the search or the evaluation

Paste `python -m termchess.bench --compare bench-final.json`:

```
```

Node counts are the signal. If this change was meant to preserve behaviour,
they should be **identical**, not merely close. If it was meant to change
behaviour, say which direction you expected and whether it went that way.

### If this changes the evaluation

- [ ] `tests/test_eval_regression.py` values regenerated **in this commit**
- [ ] Every new term is colour-symmetric

## Anything you are unsure about

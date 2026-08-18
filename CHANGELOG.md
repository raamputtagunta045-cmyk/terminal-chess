# Changelog

All notable changes to this project are documented here. Benchmark figures are
measured, never estimated.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.3.0] — 2026-08-18

A near-total rework of the engine: **89.3% fewer nodes** to reach the same
depths and a **9.50× speedup**, with move generation still verified exact
against published perft counts.

### Added

- **Transposition table** with Zobrist hashing, depth-preferred replacement,
  EXACT/LOWER/UPPER bounds and ply-corrected mate scores.
- **Null-move pruning**, **late move reductions**, **mate-distance pruning**
  and **delta pruning** in quiescence.
- **Killer moves** and a **history heuristic**, on top of existing MVV-LVA.
- **Repetition detection inside the search**, so the engine can see a
  perpetual. `Engine.choose()` accepts the game's position history.
- **Principal variation** extraction, reported by the engine and the CLI.
- **Tapered evaluation** between middlegame and endgame readings, with passed,
  backward, isolated and doubled pawns, rook files and a king pawn shield.
- **PGN import and export**, with lenient parsing and strict output.
- **`analyze`** mode, in-game and as `python chess_game.py --analyze "<FEN>"`.
- CLI commands: `analyze`, `eval`, `hint`, `go`, `perft`, `history`, `setfen`,
  `depth`, `time`, `save`, `load`; captured pieces shown alongside the board.
- **Benchmark harness** (`python -m termchess.bench`) with JSON output and
  before/after comparison.
- Ruff, mypy, a four-job CI pipeline, and this changelog.

### Changed

- Split the single `chess_game.py` into the **`termchess` package**.
  `chess_game.py` remains the entry point and re-exports the public API, so
  `python chess_game.py` and `from chess_game import Board` are unaffected.
- Search converted from **fail-hard to fail-soft** alpha-beta.
- Board representation rebuilt around precomputed tables, removing 4.36 million
  `.upper()`/`.isupper()` calls per benchmark run.
- Material, king squares and mating-material counts maintained incrementally.
- **Difficulty levels corrected.** Brutal previously advertised depth 8 while
  never exceeding 6, making it identical to Hard. The levels now reach 3/6/7/8
  from the start position — measured, not asserted.
- Tests grew from 192 to 523, at 92% coverage of the package.

### Fixed

- **Passed pawns compared against the wrong end of the enemy pawn file**, so an
  enemy doubled pawn could mask a blockade and a plainly blocked pawn collected
  the full passer bonus. Colour-symmetric, and therefore invisible to the
  symmetry suite.
- **Game-level repetition was dead in the shipped game** — the CLI tracked SAN
  strings, not position hashes, and never passed history to the engine.
- **Checkmate on the hundredth half-move scored as a draw**, because the
  fifty-move check preempted the mate check.
- `npieces` was decremented for a captured king that was never counted.
- The reported principal variation was extracted before the blunder setting
  chose a different move, so weakened levels explained themselves with a line
  they had not played.
- `ENDGAME_MATERIAL` was dead and silently duplicated inside the search.

## [0.1.0] — 2026-08-17

Initial version: a complete chess game with a built-in engine in a single file.
Iterative-deepening negamax, alpha-beta, quiescence, MVV-LVA ordering,
piece-square evaluation, full rules including castling, en passant, promotion
and every draw condition, and perft validation to depth 5.

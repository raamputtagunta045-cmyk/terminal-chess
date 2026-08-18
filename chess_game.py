#!/usr/bin/env python3
"""Terminal chess -- play a full game against a built-in engine.

Run:
    python chess_game.py
    python chess_game.py --benchmark

Enter moves as coordinates (e2e4, e7e8q) or algebraic notation
(e4, Nf3, exd5, O-O, e8=Q).

Commands: help, board, moves, undo, fen, flip, new, quit

The implementation lives in the `termchess` package. This module stays as the
entry point named in the README, and re-exports the public API so that
`from chess_game import Board, Engine, ...` keeps working exactly as before.
"""

import sys

from termchess import (
    Board,
    Engine,
    FILES,
    MATE,
    PST,
    RANKS,
    START,
    TimeUp,
    VALUES,
    __version__,
    attacked,
    evaluate,
    legal_moves,
    move_to_san,
    parse_move,
    perft,
    pseudo_moves,
    square_index,
    square_name,
)
from termchess.cli import (
    GLYPHS,
    HELP,
    LEVELS,
    USE_GLYPHS,
    ask,
    game_over,
    main,
    render,
)
from termchess.evaluate import KING_ENDGAME

__all__ = [
    "Board",
    "Engine",
    "TimeUp",
    "MATE",
    "START",
    "FILES",
    "RANKS",
    "PST",
    "KING_ENDGAME",
    "VALUES",
    "GLYPHS",
    "USE_GLYPHS",
    "HELP",
    "LEVELS",
    "ask",
    "attacked",
    "evaluate",
    "game_over",
    "legal_moves",
    "main",
    "move_to_san",
    "parse_move",
    "perft",
    "pseudo_moves",
    "render",
    "square_index",
    "square_name",
    "__version__",
]


if __name__ == "__main__":
    if "--benchmark" in sys.argv:
        from termchess.bench import main as bench_main
        sys.exit(bench_main([a for a in sys.argv[1:] if a != "--benchmark"]))
    main()

"""Terminal chess -- a complete chess game with a built-in engine.

Dependency-free: standard library only.

    from termchess import Board, Engine
    board = Board.from_fen("...")
    move, score, depth = Engine(depth=5).choose(board)

The package is layered, each module importing only from those above it:

    constants   board geometry, no internal imports at all
    board       position state, make/unmake, FEN
    movegen     pseudo-legal generation, attack detection, legality filter
    evaluate    static scoring
    search      negamax, alpha-beta, quiescence, iterative deepening
    notation    SAN generation and parsing
    perft       move-generation verification
    pgn         game import and export
    analyze     position analysis reporting
    cli         rendering and the interactive loop
"""

from .analyze import analyse, render_analysis
from .board import Board
from .constants import (
    FILES,
    MATE,
    RANKS,
    START,
    square_index,
    square_name,
)
from .evaluate import PST, VALUES, evaluate
from .movegen import attacked, legal_moves, pseudo_moves
from .notation import move_to_san, parse_move
from .perft import perft
from .pgn import export_pgn, load_pgn, parse_pgn, replay
from .search import Engine, TimeUp

__version__ = "0.3.0"

__all__ = [
    "Board",
    "Engine",
    "TimeUp",
    "MATE",
    "START",
    "FILES",
    "RANKS",
    "PST",
    "VALUES",
    "attacked",
    "evaluate",
    "legal_moves",
    "move_to_san",
    "parse_move",
    "perft",
    "analyse",
    "render_analysis",
    "export_pgn",
    "load_pgn",
    "parse_pgn",
    "replay",
    "pseudo_moves",
    "square_index",
    "square_name",
    "__version__",
]

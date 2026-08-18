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
    cli         rendering and the interactive loop
"""

from .board import Board
from .constants import (
    FILES, MATE, RANKS, START, square_index, square_name,
)
from .evaluate import PST, VALUES, evaluate
from .movegen import attacked, legal_moves, pseudo_moves
from .notation import move_to_san, parse_move
from .perft import perft
from .search import Engine, TimeUp

__version__ = "0.2.0"

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
    "pseudo_moves",
    "square_index",
    "square_name",
    "__version__",
]

"""Board geometry and shared constants.

This module deliberately imports nothing from the rest of the package. Every
other module may import it freely, which is what keeps the dependency graph
acyclic: constants <- board <- movegen <- search <- cli.

Board layout: squares[0] == a8, squares[7] == h8, squares[63] == h1.
Uppercase = white, lowercase = black, '.' = empty. Rank 8 comes first so the
list lines up with FEN placement order.
"""

START = ("rnbqkbnr"
         "pppppppp"
         "........"
         "........"
         "........"
         "........"
         "PPPPPPPP"
         "RNBQKBNR")

FILES = "abcdefgh"
RANKS = "87654321"

KNIGHT_DELTAS = ((-2, -1), (-2, 1), (-1, -2), (-1, 2),
                 (1, -2), (1, 2), (2, -1), (2, 1))
KING_DELTAS = ((-1, -1), (-1, 0), (-1, 1), (0, -1),
               (0, 1), (1, -1), (1, 0), (1, 1))
ROOK_DIRS = ((-1, 0), (1, 0), (0, -1), (0, 1))
BISHOP_DIRS = ((-1, -1), (-1, 1), (1, -1), (1, 1))
QUEEN_DIRS = ROOK_DIRS + BISHOP_DIRS

# Score of being mated. Large enough to dominate any material evaluation, small
# enough that MATE * 2 (used as an infinite search window) stays comfortable.
MATE = 100000


def square_name(s):
    """0 -> 'a8', 63 -> 'h1'."""
    return FILES[s % 8] + RANKS[s // 8]


def square_index(name):
    """'a8' -> 0, 'h1' -> 63."""
    return RANKS.index(name[1]) * 8 + FILES.index(name[0])

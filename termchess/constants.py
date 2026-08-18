"""Board geometry and shared constants.

This module deliberately imports nothing from the rest of the package. Every
other module may import it freely, which is what keeps the dependency graph
acyclic: constants <- board <- movegen <- search <- cli.

Board layout: squares[0] == a8, squares[7] == h8, squares[63] == h1.
Uppercase = white, lowercase = black, '.' = empty. Rank 8 comes first so the
list lines up with FEN placement order.
"""

import random as _random

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


# --------------------------------------------------------------------------
# Precomputed square tables
#
# The board never changes shape, so every "where can a knight on e4 go" and
# "which squares lie north-east of e4" question has a fixed answer. Computing
# them once at import turns the innermost loops of move generation and attack
# detection from arithmetic-plus-bounds-checking into a single list index.
#
# Generation order is preserved exactly: each table is built by walking the
# same delta tuples in the same order the original inline loops used, so the
# move list comes out in an identical order and the search explores an
# identical tree.
# --------------------------------------------------------------------------

def _step_targets(deltas):
    """For each square, the in-bounds squares reachable by one of `deltas`."""
    table = []
    for s in range(64):
        r, f = divmod(s, 8)
        targets = []
        for dr, df in deltas:
            rr, ff = r + dr, f + df
            if 0 <= rr < 8 and 0 <= ff < 8:
                targets.append(rr * 8 + ff)
        table.append(tuple(targets))
    return tuple(table)


def _rays(dirs):
    """For each square, one tuple of squares per direction, nearest first.

    Sliding pieces need to stop at the first occupied square, so the ray has to
    stay ordered rather than collapsing into a set.
    """
    table = []
    for s in range(64):
        r, f = divmod(s, 8)
        per_direction = []
        for dr, df in dirs:
            ray = []
            rr, ff = r + dr, f + df
            while 0 <= rr < 8 and 0 <= ff < 8:
                ray.append(rr * 8 + ff)
                rr += dr
                ff += df
            per_direction.append(tuple(ray))
        table.append(tuple(per_direction))
    return tuple(table)


KNIGHT_TARGETS = _step_targets(KNIGHT_DELTAS)
KING_TARGETS = _step_targets(KING_DELTAS)

ROOK_RAYS = _rays(ROOK_DIRS)
BISHOP_RAYS = _rays(BISHOP_DIRS)
QUEEN_RAYS = _rays(QUEEN_DIRS)

# Rays indexed by piece letter, so the generator can look up the right set
# without branching on piece type.
RAYS_FOR = {'R': ROOK_RAYS, 'B': BISHOP_RAYS, 'Q': QUEEN_RAYS}


def _pawn_attackers(by_white):
    """Squares a pawn of the given colour must stand on to attack square s.

    Attack detection asks the question backwards -- 'is s attacked?' -- so this
    is the inverse of where a pawn captures to.
    """
    table = []
    for s in range(64):
        r, f = divmod(s, 8)
        # A white pawn attacks upward (toward rank 8, lower index), so an
        # attacker of s sits one rank below it.
        pr = r + 1 if by_white else r - 1
        squares = []
        if 0 <= pr < 8:
            for pf in (f - 1, f + 1):
                if 0 <= pf < 8:
                    squares.append(pr * 8 + pf)
        table.append(tuple(squares))
    return tuple(table)


WHITE_PAWN_ATTACKERS = _pawn_attackers(True)
BLACK_PAWN_ATTACKERS = _pawn_attackers(False)

# Piece classification by raw character, so the hot paths never call
# .upper() or .isupper(). Those two methods alone accounted for 4.36 million
# calls and 15% of runtime in the depth-5 profile.
WHITE_PIECES = frozenset('PNBRQK')
BLACK_PIECES = frozenset('pnbrqk')
IS_WHITE = {c: True for c in WHITE_PIECES}
IS_WHITE.update({c: False for c in BLACK_PIECES})
UPPER = {c: c for c in WHITE_PIECES}
UPPER.update({c: c.upper() for c in BLACK_PIECES})

ALL_PIECES = 'PNBRQKpnbrqk'

# Material values, indexed by uppercase letter. Lives here rather than in
# evaluate.py because the board tracks material incrementally and the search
# uses it for capture ordering, so it is not purely an evaluation concern.
PIECE_VALUE = {'P': 100, 'N': 320, 'B': 330, 'R': 500, 'Q': 900, 'K': 0}

# Non-pawn, non-king material contributed by each piece character. Summing
# this over the board gives the number the endgame test compares against, and
# because it is keyed by the raw character it can be applied as a delta in
# make()/unmake() instead of rescanning 64 squares per evaluation.
HEAVY_VALUE = {c: (PIECE_VALUE[UPPER[c]] if UPPER[c] in 'NBRQ' else 0)
               for c in ALL_PIECES}
HEAVY_VALUE['.'] = 0

# A pawn, rook or queen can always force mate; a lone minor piece cannot.
IS_PRQ = {c: UPPER[c] in 'PRQ' for c in ALL_PIECES}
IS_PRQ['.'] = False

IS_KING = {c: UPPER[c] == 'K' for c in ALL_PIECES}
IS_KING['.'] = False

# Material value keyed by the raw character, for capture ordering in search.
CHAR_VALUE = {c: PIECE_VALUE[UPPER[c]] for c in ALL_PIECES}
CHAR_VALUE['.'] = 0

# Castling rights lost by moving a given piece, and the right associated with
# each corner square. Used to decide whether make() needs to touch the rights
# at all -- most moves do not, and copying the set regardless was costing an
# allocation on every one of ~145,000 make() calls per search.
CASTLE_LOSS_BY_PIECE = {'K': frozenset('KQ'), 'k': frozenset('kq')}
CORNER_RIGHT = {63: 'K', 56: 'Q', 7: 'k', 0: 'q'}


# --------------------------------------------------------------------------
# Zobrist hashing
#
# Each (piece, square) pair, each castling right, each en-passant file and the
# side to move gets a random 64-bit number. A position's hash is the XOR of the
# numbers for everything true about it. Because XOR is its own inverse, moving a
# piece is two XORs rather than a rescan of the board -- which is what makes a
# transposition table affordable.
#
# The generator is seeded, so hashes are identical across runs and machines.
# That keeps the transposition table deterministic and lets tests assert on
# concrete hash behaviour rather than only on self-consistency.
# --------------------------------------------------------------------------

def _zobrist_tables(seed=0x9E3779B97F4A7C15):
    rng = _random.Random(seed)

    def rand():
        return rng.getrandbits(64)

    pieces = {c: tuple(rand() for _ in range(64)) for c in ALL_PIECES}
    castling = {r: rand() for r in 'KQkq'}
    ep_file = tuple(rand() for _ in range(8))
    side = rand()
    return pieces, castling, ep_file, side


ZOBRIST_PIECE, ZOBRIST_CASTLING, ZOBRIST_EP_FILE, ZOBRIST_SIDE = _zobrist_tables()

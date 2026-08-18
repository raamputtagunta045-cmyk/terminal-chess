"""Static position evaluation.

Returns centipawns from White's point of view, always -- positive is good for
White regardless of whose turn it is. The search applies the side-to-move sign
itself; if this function ever became side-relative, negamax would double up the
sign and the engine would start helping its opponent.

Every term must be colour-symmetric: a position and its mirror image must score
as exact negatives. tests/test_eval_symmetry.py enforces that.
"""

from .constants import PIECE_VALUE

VALUES = PIECE_VALUE

# Piece-square tables, written from White's perspective with rank 8 first, so
# they index the squares list directly. Black reads the same table through the
# index flip s ^ 56, which mirrors the rank while preserving the file.
PST = {
    'P': (0, 0, 0, 0, 0, 0, 0, 0,
          50, 50, 50, 50, 50, 50, 50, 50,
          10, 10, 20, 30, 30, 20, 10, 10,
          5, 5, 10, 25, 25, 10, 5, 5,
          0, 0, 0, 20, 20, 0, 0, 0,
          5, -5, -10, 0, 0, -10, -5, 5,
          5, 10, 10, -20, -20, 10, 10, 5,
          0, 0, 0, 0, 0, 0, 0, 0),
    'N': (-50, -40, -30, -30, -30, -30, -40, -50,
          -40, -20, 0, 0, 0, 0, -20, -40,
          -30, 0, 10, 15, 15, 10, 0, -30,
          -30, 5, 15, 20, 20, 15, 5, -30,
          -30, 0, 15, 20, 20, 15, 0, -30,
          -30, 5, 10, 15, 15, 10, 5, -30,
          -40, -20, 0, 5, 5, 0, -20, -40,
          -50, -40, -30, -30, -30, -30, -40, -50),
    'B': (-20, -10, -10, -10, -10, -10, -10, -20,
          -10, 0, 0, 0, 0, 0, 0, -10,
          -10, 0, 5, 10, 10, 5, 0, -10,
          -10, 5, 5, 10, 10, 5, 5, -10,
          -10, 0, 10, 10, 10, 10, 0, -10,
          -10, 10, 10, 10, 10, 10, 10, -10,
          -10, 5, 0, 0, 0, 0, 5, -10,
          -20, -10, -10, -10, -10, -10, -10, -20),
    'R': (0, 0, 0, 0, 0, 0, 0, 0,
          5, 10, 10, 10, 10, 10, 10, 5,
          -5, 0, 0, 0, 0, 0, 0, -5,
          -5, 0, 0, 0, 0, 0, 0, -5,
          -5, 0, 0, 0, 0, 0, 0, -5,
          -5, 0, 0, 0, 0, 0, 0, -5,
          -5, 0, 0, 0, 0, 0, 0, -5,
          0, 0, 0, 5, 5, 0, 0, 0),
    'Q': (-20, -10, -10, -5, -5, -10, -10, -20,
          -10, 0, 0, 0, 0, 0, 0, -10,
          -10, 0, 5, 5, 5, 5, 0, -10,
          -5, 0, 5, 5, 5, 5, 0, -5,
          0, 0, 5, 5, 5, 5, 0, -5,
          -10, 5, 5, 5, 5, 5, 0, -10,
          -10, 0, 5, 0, 0, 0, 0, -10,
          -20, -10, -10, -5, -5, -10, -10, -20),
    'K': (-30, -40, -40, -50, -50, -40, -40, -30,
          -30, -40, -40, -50, -50, -40, -40, -30,
          -30, -40, -40, -50, -50, -40, -40, -30,
          -30, -40, -40, -50, -50, -40, -40, -30,
          -20, -30, -30, -40, -40, -30, -30, -20,
          -10, -20, -20, -20, -20, -20, -20, -10,
          20, 20, 0, 0, 0, 0, 20, 20,
          20, 30, 10, 0, 0, 10, 30, 20),
}

# With the heavy pieces gone the king stops hiding and becomes a fighting
# piece, so it wants the centre instead of the corner.
KING_ENDGAME = (-50, -40, -30, -20, -20, -30, -40, -50,
                -30, -20, -10, 0, 0, -10, -20, -30,
                -30, -10, 20, 30, 30, 20, -10, -30,
                -30, -10, 30, 40, 40, 30, -10, -30,
                -30, -10, 30, 40, 40, 30, -10, -30,
                -30, -10, 20, 30, 30, 20, -10, -30,
                -30, -30, 0, 0, 0, 0, -30, -30,
                -50, -30, -30, -30, -30, -30, -30, -50)

# Total non-pawn, non-king material below which the position counts as an
# endgame. Roughly a queen and a minor piece per side.
ENDGAME_MATERIAL = 1300

DOUBLED_PAWN_PENALTY = 15
ISOLATED_PAWN_PENALTY = 12
BISHOP_PAIR_BONUS = 30


def _combined_tables(king_table):
    """Fold material value, piece-square bonus and colour sign into one table.

    Evaluation asked three questions per square -- what colour is this, what
    kind of piece is it, where does that piece want to be -- and answered them
    with .isupper(), .upper() and a table lookup. All three have fixed answers
    for a given (character, square) pair, so they are folded into a single
    signed number here and the inner loop becomes `score += table[p][s]`.

    Black's entry is the negated white value read through the mirrored index
    s ^ 56, exactly as the original computed it, which is also what keeps the
    evaluation colour-symmetric by construction.
    """
    tables = {}
    for u in 'PNBRQK':
        pst = king_table if u == 'K' else PST[u]
        tables[u] = tuple(VALUES[u] + pst[s] for s in range(64))
        tables[u.lower()] = tuple(-(VALUES[u] + pst[s ^ 56]) for s in range(64))
    return tables


MIDGAME_SCORE = _combined_tables(PST['K'])
ENDGAME_SCORE = _combined_tables(KING_ENDGAME)


def evaluate(board):
    """Static score in centipawns, positive = good for white."""
    b = board.squares
    # board.heavy is maintained incrementally by make/unmake, so the endgame
    # test no longer costs a full scan of its own before the real one starts.
    table = ENDGAME_SCORE if board.heavy < ENDGAME_MATERIAL else MIDGAME_SCORE

    score = 0
    white_bishops = 0
    black_bishops = 0
    wf = [0] * 8
    bf = [0] * 8

    for s, p in enumerate(b):
        if p == '.':
            continue
        score += table[p][s]
        if p == 'P':
            wf[s & 7] += 1
        elif p == 'p':
            bf[s & 7] += 1
        elif p == 'B':
            white_bishops += 1
        elif p == 'b':
            black_bishops += 1

    if white_bishops >= 2:
        score += BISHOP_PAIR_BONUS
    if black_bishops >= 2:
        score -= BISHOP_PAIR_BONUS

    for files, sign in ((wf, 1), (bf, -1)):
        for f, count in enumerate(files):
            if not count:
                continue
            if count > 1:
                score -= sign * DOUBLED_PAWN_PENALTY * (count - 1)
            # Isolated: no friendly pawn on either adjacent file.
            if not (f and files[f - 1]) and not (f < 7 and files[f + 1]):
                score -= sign * ISOLATED_PAWN_PENALTY
    return score

"""Static position evaluation.

Returns centipawns from White's point of view, always -- positive is good for
White regardless of whose turn it is. The search applies the side-to-move sign
itself; if this function ever became side-relative, negamax would double up the
sign and the engine would start helping its opponent.

Every term must be colour-symmetric: a position and its mirror image must score
as exact negatives. tests/test_eval_symmetry.py enforces that.
"""

VALUES = {'P': 100, 'N': 320, 'B': 330, 'R': 500, 'Q': 900, 'K': 0}

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


def evaluate(board):
    """Static score in centipawns, positive = good for white."""
    b = board.squares
    score = 0
    bishops = [0, 0]
    pawn_files = [[0] * 8, [0] * 8]
    heavy = 0

    for p in b:
        if p not in '.PpKk':
            heavy += VALUES[p.upper()]
    endgame = heavy < ENDGAME_MATERIAL

    for s, p in enumerate(b):
        if p == '.':
            continue
        white = p.isupper()
        u = p.upper()
        idx = s if white else s ^ 56
        table = KING_ENDGAME if (u == 'K' and endgame) else PST[u]
        val = VALUES[u] + table[idx]
        score += val if white else -val
        if u == 'B':
            bishops[0 if white else 1] += 1
        elif u == 'P':
            pawn_files[0 if white else 1][s % 8] += 1

    if bishops[0] >= 2:
        score += BISHOP_PAIR_BONUS
    if bishops[1] >= 2:
        score -= BISHOP_PAIR_BONUS

    for side, sign in ((0, 1), (1, -1)):
        files = pawn_files[side]
        for f, count in enumerate(files):
            if count > 1:
                score -= sign * DOUBLED_PAWN_PENALTY * (count - 1)
            if count and not (f and files[f - 1]) and not (f < 7 and files[f + 1]):
                score -= sign * ISOLATED_PAWN_PENALTY
    return score

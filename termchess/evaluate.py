"""Static position evaluation.

Returns centipawns from White's point of view, always -- positive is good for
White regardless of whose turn it is. The search applies the side-to-move sign
itself; if this function ever became side-relative, negamax would double up the
sign and the engine would start helping its opponent.

Every term must be colour-symmetric: a position and its mirror image must score
as exact negatives. tests/test_eval_symmetry.py enforces that.
"""

from .constants import ALL_PIECES, PIECE_VALUE, UPPER

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

# --------------------------------------------------------------------------
# Tapered evaluation
#
# A position is not simply "middlegame" or "endgame"; it slides between them as
# pieces come off. The previous evaluation flipped the king's table the instant
# non-pawn material crossed 1300cp, which is a real defect: a single capture
# could swing the score by tens of centipawns for no positional reason, and the
# search would chase that discontinuity.
#
# Instead every position gets a phase from 24 (all pieces on) down to 0 (bare
# kings and pawns), and the score is interpolated between a middlegame and an
# endgame reading. Terms that only matter in one regime -- king safety in the
# middlegame, passed pawns in the endgame -- are weighted into the reading
# where they belong, which is what tapering is really for.
# --------------------------------------------------------------------------

PHASE_WEIGHT = {'N': 1, 'B': 1, 'R': 2, 'Q': 4, 'P': 0, 'K': 0}
PHASE_OF = {c: PHASE_WEIGHT[UPPER[c]] for c in ALL_PIECES}
TOTAL_PHASE = 24            # 4 knights + 4 bishops + 4 rooks(2) + 2 queens(4)

# Non-pawn, non-king material below which the search treats the position as an
# endgame (used by delta pruning, which is unsound in a bare endgame).
ENDGAME_MATERIAL = 1300

# In the endgame a pawn's only job is to promote, so advancement is worth far
# more than the central-control shape that suits the middlegame.
PAWN_ENDGAME = (0, 0, 0, 0, 0, 0, 0, 0,
                90, 90, 90, 90, 90, 90, 90, 90,
                55, 55, 55, 55, 55, 55, 55, 55,
                30, 30, 30, 30, 30, 30, 30, 30,
                15, 15, 15, 15, 15, 15, 15, 15,
                5, 5, 5, 5, 5, 5, 5, 5,
                0, 0, 0, 0, 0, 0, 0, 0,
                0, 0, 0, 0, 0, 0, 0, 0)

DOUBLED_PAWN_PENALTY = 15
ISOLATED_PAWN_PENALTY = 12
BACKWARD_PAWN_PENALTY = 8
BISHOP_PAIR_BONUS = 30
ROOK_OPEN_FILE = 25
ROOK_SEMI_OPEN_FILE = 12
KING_SHIELD_PENALTY = 12

# Passed-pawn bonus by how far the pawn has advanced (0 = home rank).
# Endgame values are far larger because an unstoppable passer simply wins,
# whereas in a full middlegame it is one feature among many.
PASSED_MG = (0, 5, 10, 20, 35, 60, 100, 0)
PASSED_EG = (0, 10, 20, 40, 70, 120, 180, 0)


def _tables(king_table, pawn_table):
    """Fold material, piece-square value and colour sign into one table.

    This turns three questions per square -- what colour, what piece, where
    does it belong -- into a single signed lookup. Black's entry is the negated
    white value read through the mirrored index, which makes colour symmetry
    structural rather than something the runtime has to remember.
    """
    out = {}
    for u in 'PNBRQK':
        pst = (king_table if u == 'K'
               else pawn_table if u == 'P' else PST[u])
        out[u] = tuple(VALUES[u] + pst[s] for s in range(64))
        out[u.lower()] = tuple(-(VALUES[u] + pst[s ^ 56]) for s in range(64))
    return out


MIDGAME_SCORE = _tables(PST['K'], PST['P'])
ENDGAME_SCORE = _tables(KING_ENDGAME, PAWN_ENDGAME)

# One lookup per piece instead of three. The inner loop needs the middlegame
# table, the endgame table and the phase weight for every occupied square;
# bundling them means a single dict hit rather than one per quantity, which
# matters at roughly two million lookups per benchmark run.
TERM = {c: (MIDGAME_SCORE[c], ENDGAME_SCORE[c], PHASE_OF[c])
        for c in ALL_PIECES}

# Advancement index for a pawn, by board row, per colour. Row 0 is rank 8, so a
# white pawn advances as its row decreases and a black pawn as its row grows.
_WHITE_ADVANCE = tuple(max(0, 6 - r) for r in range(8))
_BLACK_ADVANCE = tuple(max(0, r - 1) for r in range(8))

_NO_PAWN = 99


def _divide(total, divisor):
    """Divide with truncation toward zero.

    Python's // floors, so -1 // 24 is -1 while 1 // 24 is 0. That asymmetry
    would break the guarantee that a mirrored position scores as the exact
    negative -- the property the whole evaluation is tested against.
    """
    if total >= 0:
        return total // divisor
    return -((-total) // divisor)


def evaluate(board):
    """Static score in centipawns, positive = good for white."""
    b = board.squares

    mg = 0
    eg = 0
    phase = 0
    white_bishops = 0
    black_bishops = 0

    wc = [0] * 8                # white pawns per file
    bc = [0] * 8
    w_front = [_NO_PAWN] * 8    # most advanced white pawn row (smallest)
    w_back = [-1] * 8           # least advanced white pawn row (largest)
    b_front = [-1] * 8          # most advanced black pawn row (largest)
    b_back = [_NO_PAWN] * 8
    white_rooks = []
    black_rooks = []

    for s, p in enumerate(b):
        if p == '.':
            continue
        mg_table, eg_table, piece_phase = TERM[p]
        mg += mg_table[s]
        eg += eg_table[s]
        phase += piece_phase

        if p == 'P':
            f = s & 7
            r = s >> 3
            wc[f] += 1
            if r < w_front[f]:
                w_front[f] = r
            if r > w_back[f]:
                w_back[f] = r
        elif p == 'p':
            f = s & 7
            r = s >> 3
            bc[f] += 1
            if r > b_front[f]:
                b_front[f] = r
            if r < b_back[f]:
                b_back[f] = r
        elif p == 'B':
            white_bishops += 1
        elif p == 'b':
            black_bishops += 1
        elif p == 'R':
            white_rooks.append(s)
        elif p == 'r':
            black_rooks.append(s)

    # -- the bishop pair -------------------------------------------------
    # Two bishops cover both colour complexes, so they are worth more than the
    # sum of their parts, and the effect persists into the endgame.
    if white_bishops >= 2:
        mg += BISHOP_PAIR_BONUS
        eg += BISHOP_PAIR_BONUS
    if black_bishops >= 2:
        mg -= BISHOP_PAIR_BONUS
        eg -= BISHOP_PAIR_BONUS

    # -- pawn structure --------------------------------------------------
    for f in range(8):
        left = f - 1
        right = f + 1

        if wc[f]:
            if wc[f] > 1:
                # Doubled pawns cannot defend each other and one of them is
                # effectively immobile.
                penalty = DOUBLED_PAWN_PENALTY * (wc[f] - 1)
                mg -= penalty
                eg -= penalty
            has_left = left >= 0 and wc[left]
            has_right = right < 8 and wc[right]
            if not has_left and not has_right:
                # Isolated: no friendly pawn can ever defend it.
                mg -= ISOLATED_PAWN_PENALTY
                eg -= ISOLATED_PAWN_PENALTY
            else:
                # Backward: both neighbours have advanced past it, so it is the
                # base of the chain and cannot be defended by a pawn.
                lb = w_back[left] if left >= 0 else -1
                rb = w_back[right] if right < 8 else -1
                if lb < w_back[f] and rb < w_back[f]:
                    mg -= BACKWARD_PAWN_PENALTY
                    eg -= BACKWARD_PAWN_PENALTY

            # Passed: no enemy pawn ahead on this file or either neighbour.
            r = w_front[f]
            blocked = False
            for ff in (left, f, right):
                if 0 <= ff < 8 and 0 <= b_front[ff] < r:
                    blocked = True
                    break
            # A doubled pawn is not a passer in any useful sense: its own
            # partner sits behind it on the same file, so the pair cannot
            # support each other's advance the way a healthy passer is
            # supported. Awarding the bonus anyway made a doubled, isolated
            # pawn score better than two healthy connected ones.
            if not blocked and wc[f] == 1:
                adv = _WHITE_ADVANCE[r]
                mg += PASSED_MG[adv]
                eg += PASSED_EG[adv]

        if bc[f]:
            if bc[f] > 1:
                penalty = DOUBLED_PAWN_PENALTY * (bc[f] - 1)
                mg += penalty
                eg += penalty
            has_left = left >= 0 and bc[left]
            has_right = right < 8 and bc[right]
            if not has_left and not has_right:
                mg += ISOLATED_PAWN_PENALTY
                eg += ISOLATED_PAWN_PENALTY
            else:
                lb = b_back[left] if left >= 0 else _NO_PAWN
                rb = b_back[right] if right < 8 else _NO_PAWN
                if lb > b_back[f] and rb > b_back[f]:
                    mg += BACKWARD_PAWN_PENALTY
                    eg += BACKWARD_PAWN_PENALTY

            r = b_front[f]
            blocked = False
            for ff in (left, f, right):
                if 0 <= ff < 8 and w_front[ff] != _NO_PAWN and w_front[ff] > r:
                    blocked = True
                    break
            if not blocked and bc[f] == 1:
                adv = _BLACK_ADVANCE[r]
                mg -= PASSED_MG[adv]
                eg -= PASSED_EG[adv]

    # -- rook activity ---------------------------------------------------
    # A rook's value is mostly the file it stands on: an open file is a road
    # into the enemy position, a blocked one is a wall.
    for s in white_rooks:
        f = s & 7
        if not wc[f]:
            bonus = ROOK_OPEN_FILE if not bc[f] else ROOK_SEMI_OPEN_FILE
            mg += bonus
            eg += bonus
    for s in black_rooks:
        f = s & 7
        if not bc[f]:
            bonus = ROOK_OPEN_FILE if not wc[f] else ROOK_SEMI_OPEN_FILE
            mg -= bonus
            eg -= bonus

    # -- king safety (middlegame only) -----------------------------------
    # Missing pawns in front of a king are only dangerous while there are
    # pieces left to exploit the draught. In the endgame the king wants to walk
    # out anyway, so this term is deliberately absent from the endgame reading
    # -- exactly the kind of thing tapering exists to express.
    wk = board.wk
    if wk >= 48:                      # ranks 1-2
        kf = wk & 7
        for ff in (kf - 1, kf, kf + 1):
            if 0 <= ff < 8 and not wc[ff]:
                mg -= KING_SHIELD_PENALTY
    bk = board.bk
    if 0 <= bk < 16:                  # ranks 7-8
        kf = bk & 7
        for ff in (kf - 1, kf, kf + 1):
            if 0 <= ff < 8 and not bc[ff]:
                mg += KING_SHIELD_PENALTY

    if phase > TOTAL_PHASE:
        phase = TOTAL_PHASE           # promotions can exceed the starting phase
    return _divide(mg * phase + eg * (TOTAL_PHASE - phase), TOTAL_PHASE)

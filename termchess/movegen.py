"""Move generation and attack detection.

These are free functions taking a board rather than methods on it, so that
search can call them directly without an attribute lookup and a bound-method
hop on every one of the hundreds of thousands of calls a search makes. `Board`
keeps thin delegating methods for the public API.

Attack detection works *backwards* from the target square -- casting rays
outward and checking what sits at the end -- instead of enumerating every enemy
move. That is what makes it cheap enough to call inside the search, once per
generated move, to filter pseudo-legal moves down to legal ones.
"""

from .constants import (
    BISHOP_DIRS, KING_DELTAS, KNIGHT_DELTAS, QUEEN_DIRS, ROOK_DIRS,
)


def attacked(board, s, by_white):
    """True if square `s` is attacked by the given side."""
    b = board.squares
    r, f = divmod(s, 8)

    pr = r + 1 if by_white else r - 1
    if 0 <= pr < 8:
        pawn = 'P' if by_white else 'p'
        for pf in (f - 1, f + 1):
            if 0 <= pf < 8 and b[pr * 8 + pf] == pawn:
                return True

    knight = 'N' if by_white else 'n'
    for dr, df in KNIGHT_DELTAS:
        rr, ff = r + dr, f + df
        if 0 <= rr < 8 and 0 <= ff < 8 and b[rr * 8 + ff] == knight:
            return True

    king = 'K' if by_white else 'k'
    for dr, df in KING_DELTAS:
        rr, ff = r + dr, f + df
        if 0 <= rr < 8 and 0 <= ff < 8 and b[rr * 8 + ff] == king:
            return True

    for dirs, names in ((ROOK_DIRS, 'RQ'), (BISHOP_DIRS, 'BQ')):
        targets = names if by_white else names.lower()
        for dr, df in dirs:
            rr, ff = r + dr, f + df
            while 0 <= rr < 8 and 0 <= ff < 8:
                p = b[rr * 8 + ff]
                if p != '.':
                    if p in targets:
                        return True
                    break
                rr += dr
                ff += df
    return False


def castle_moves(board, s, white):
    """Castling moves for a king standing on `s`, if rights and geometry allow.

    Checks the three squares that matter: the king must not be in check, must
    not pass through an attacked square, and must not land on one. The rook's
    transit square is deliberately *not* checked -- it may be attacked.
    """
    b = board.squares
    out = []
    home, rook, ks, qs = (60, 'R', 'K', 'Q') if white else (4, 'r', 'k', 'q')
    if s != home:
        return out
    if attacked(board, home, not white):
        return out
    if (ks in board.castling and b[home + 1] == '.' and b[home + 2] == '.'
            and b[home + 3] == rook
            and not attacked(board, home + 1, not white)
            and not attacked(board, home + 2, not white)):
        out.append((home, home + 2, None))
    if (qs in board.castling and b[home - 1] == '.' and b[home - 2] == '.'
            and b[home - 3] == '.' and b[home - 4] == rook
            and not attacked(board, home - 1, not white)
            and not attacked(board, home - 2, not white)):
        out.append((home, home - 2, None))
    return out


def pseudo_moves(board):
    """Every move that obeys piece movement rules, legal or not.

    Moves that leave the mover's own king in check are still included here;
    legal_moves() filters them out.
    """
    b = board.squares
    white = board.white_to_move
    moves = []

    for s, p in enumerate(b):
        if p == '.' or p.isupper() != white:
            continue
        r, f = divmod(s, 8)
        u = p.upper()

        if u == 'P':
            d = -1 if white else 1
            start_rank = 6 if white else 1
            last_rank = 0 if white else 7
            r1 = r + d
            if 0 <= r1 < 8:
                if b[r1 * 8 + f] == '.':
                    if r1 == last_rank:
                        for pr in 'QRBN':
                            moves.append((s, r1 * 8 + f, pr))
                    else:
                        moves.append((s, r1 * 8 + f, None))
                        r2 = r + 2 * d
                        if r == start_rank and b[r2 * 8 + f] == '.':
                            moves.append((s, r2 * 8 + f, None))
                for df in (-1, 1):
                    ff = f + df
                    if not 0 <= ff < 8:
                        continue
                    t = r1 * 8 + ff
                    tp = b[t]
                    if (tp != '.' and tp.isupper() != white) or t == board.ep:
                        if r1 == last_rank:
                            for pr in 'QRBN':
                                moves.append((s, t, pr))
                        else:
                            moves.append((s, t, None))

        elif u == 'N':
            for dr, df in KNIGHT_DELTAS:
                rr, ff = r + dr, f + df
                if 0 <= rr < 8 and 0 <= ff < 8:
                    t = rr * 8 + ff
                    if b[t] == '.' or b[t].isupper() != white:
                        moves.append((s, t, None))

        elif u == 'K':
            for dr, df in KING_DELTAS:
                rr, ff = r + dr, f + df
                if 0 <= rr < 8 and 0 <= ff < 8:
                    t = rr * 8 + ff
                    if b[t] == '.' or b[t].isupper() != white:
                        moves.append((s, t, None))
            moves.extend(castle_moves(board, s, white))

        else:
            dirs = (ROOK_DIRS if u == 'R'
                    else BISHOP_DIRS if u == 'B' else QUEEN_DIRS)
            for dr, df in dirs:
                rr, ff = r + dr, f + df
                while 0 <= rr < 8 and 0 <= ff < 8:
                    t = rr * 8 + ff
                    tp = b[t]
                    if tp == '.':
                        moves.append((s, t, None))
                    else:
                        if tp.isupper() != white:
                            moves.append((s, t, None))
                        break
                    rr += dr
                    ff += df
    return moves


def legal_moves(board):
    """Pseudo-legal moves filtered by actually playing each one.

    Playing the move and asking whether the king is attacked is slower per move
    than dedicated pin detection, but it is impossible to get subtly wrong --
    which is why perft agrees with the reference counts.
    """
    white = board.white_to_move
    out = []
    for m in pseudo_moves(board):
        undo = board.make(m)
        if not attacked(board, board.king_sq(white), not white):
            out.append(m)
        board.unmake(undo)
    return out

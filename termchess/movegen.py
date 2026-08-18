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
    BISHOP_RAYS,
    BLACK_PAWN_ATTACKERS,
    BLACK_PIECES,
    KING_TARGETS,
    KNIGHT_TARGETS,
    RAYS_FOR,
    ROOK_RAYS,
    UPPER,
    WHITE_PAWN_ATTACKERS,
    WHITE_PIECES,
)


def attacked(board, s, by_white):
    """True if square `s` is attacked by the given side.

    Walks precomputed target lists and rays rather than recomputing rank/file
    arithmetic and bounds checks on every call -- this runs well over a hundred
    thousand times per search.
    """
    b = board.squares

    if by_white:
        for a in WHITE_PAWN_ATTACKERS[s]:
            if b[a] == 'P':
                return True
        knight, king, straight, diagonal = 'N', 'K', 'RQ', 'BQ'
    else:
        for a in BLACK_PAWN_ATTACKERS[s]:
            if b[a] == 'p':
                return True
        knight, king, straight, diagonal = 'n', 'k', 'rq', 'bq'

    for t in KNIGHT_TARGETS[s]:
        if b[t] == knight:
            return True

    for t in KING_TARGETS[s]:
        if b[t] == king:
            return True

    for rays, targets in ((ROOK_RAYS[s], straight), (BISHOP_RAYS[s], diagonal)):
        for ray in rays:
            for t in ray:
                p = b[t]
                if p != '.':
                    if p in targets:
                        return True
                    break
    return False


def castle_moves(board, s, white):
    """Castling moves for a king standing on `s`, if rights and geometry allow.

    Checks the three squares that matter: the king must not be in check, must
    not pass through an attacked square, and must not land on one. The rook's
    transit square is deliberately *not* checked -- it may be attacked.
    """
    b = board.squares
    out = []          # type: list
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
    ep = board.ep
    own = WHITE_PIECES if white else BLACK_PIECES
    moves = []        # type: list
    append = moves.append

    for s, p in enumerate(b):
        if p not in own:
            continue
        u = UPPER[p]

        if u == 'P':
            r, f = divmod(s, 8)
            d = -1 if white else 1
            start_rank = 6 if white else 1
            last_rank = 0 if white else 7
            r1 = r + d
            if 0 <= r1 < 8:
                if b[r1 * 8 + f] == '.':
                    if r1 == last_rank:
                        for pr in 'QRBN':
                            append((s, r1 * 8 + f, pr))
                    else:
                        append((s, r1 * 8 + f, None))
                        r2 = r + 2 * d
                        if r == start_rank and b[r2 * 8 + f] == '.':
                            append((s, r2 * 8 + f, None))
                for df in (-1, 1):
                    ff = f + df
                    if not 0 <= ff < 8:
                        continue
                    t = r1 * 8 + ff
                    tp = b[t]
                    if (tp != '.' and tp not in own) or t == ep:
                        if r1 == last_rank:
                            for pr in 'QRBN':
                                append((s, t, pr))
                        else:
                            append((s, t, None))

        elif u == 'N':
            for t in KNIGHT_TARGETS[s]:
                if b[t] not in own:
                    append((s, t, None))

        elif u == 'K':
            for t in KING_TARGETS[s]:
                if b[t] not in own:
                    append((s, t, None))
            moves.extend(castle_moves(board, s, white))

        else:
            for ray in RAYS_FOR[u][s]:
                for t in ray:
                    tp = b[t]
                    if tp == '.':
                        append((s, t, None))
                    else:
                        if tp not in own:
                            append((s, t, None))
                        break
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

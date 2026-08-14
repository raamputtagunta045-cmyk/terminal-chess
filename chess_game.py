#!/usr/bin/env python3
"""Terminal chess -- play a full game against a built-in engine.

Run:
    python chess_game.py

Enter moves as coordinates (e2e4, e7e8q) or algebraic notation
(e4, Nf3, exd5, O-O, e8=Q).

Commands: help, board, moves, undo, fen, flip, new, quit
"""

import sys
import time
import random

# --------------------------------------------------------------------------
# Board layout: squares[0] == a8, squares[7] == h8, squares[63] == h1.
# Uppercase = white, lowercase = black, '.' = empty.
# --------------------------------------------------------------------------

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


def square_name(s):
    return FILES[s % 8] + RANKS[s // 8]


def square_index(name):
    return RANKS.index(name[1]) * 8 + FILES.index(name[0])


class Board:
    """Full chess position with make/unmake for search."""

    def __init__(self):
        self.squares = list(START)
        self.white_to_move = True
        self.castling = {'K', 'Q', 'k', 'q'}
        self.ep = None
        self.halfmove = 0
        self.fullmove = 1

    # -- queries ---------------------------------------------------------

    def key(self):
        return (''.join(self.squares), self.white_to_move,
                frozenset(self.castling), self.ep)

    def king_sq(self, white):
        return self.squares.index('K' if white else 'k')

    def in_check(self, white):
        return self.attacked(self.king_sq(white), not white)

    def attacked(self, s, by_white):
        """True if square `s` is attacked by the given side."""
        b = self.squares
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

    # -- move generation -------------------------------------------------

    def gen_pseudo(self):
        b = self.squares
        white = self.white_to_move
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
                        if (tp != '.' and tp.isupper() != white) or t == self.ep:
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
                moves.extend(self._castles(s, white))

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

    def _castles(self, s, white):
        b = self.squares
        out = []
        home, rook, ks, qs = (60, 'R', 'K', 'Q') if white else (4, 'r', 'k', 'q')
        if s != home:
            return out
        if self.attacked(home, not white):
            return out
        if (ks in self.castling and b[home + 1] == '.' and b[home + 2] == '.'
                and b[home + 3] == rook
                and not self.attacked(home + 1, not white)
                and not self.attacked(home + 2, not white)):
            out.append((home, home + 2, None))
        if (qs in self.castling and b[home - 1] == '.' and b[home - 2] == '.'
                and b[home - 3] == '.' and b[home - 4] == rook
                and not self.attacked(home - 1, not white)
                and not self.attacked(home - 2, not white)):
            out.append((home, home - 2, None))
        return out

    def legal_moves(self):
        white = self.white_to_move
        out = []
        for m in self.gen_pseudo():
            undo = self.make(m)
            if not self.attacked(self.king_sq(white), not white):
                out.append(m)
            self.unmake(undo)
        return out

    # -- make / unmake ---------------------------------------------------

    def make(self, mv):
        frm, to, promo = mv
        b = self.squares
        piece = b[frm]
        white = piece.isupper()
        captured = b[to]
        cap_sq = to
        rook_move = None

        if piece in 'Pp' and to == self.ep and captured == '.':
            cap_sq = to + (8 if white else -8)
            captured = b[cap_sq]
            b[cap_sq] = '.'

        undo = (frm, to, promo, captured, cap_sq, set(self.castling),
                self.ep, self.halfmove, self.fullmove, None)

        b[to] = promo.upper() if promo and white else (
            promo.lower() if promo else piece)
        b[frm] = '.'

        if piece in 'Kk' and abs(to - frm) == 2:
            if to > frm:
                rf, rt = frm + 3, frm + 1
            else:
                rf, rt = frm - 4, frm - 1
            b[rt] = b[rf]
            b[rf] = '.'
            rook_move = (rf, rt)
            undo = undo[:9] + (rook_move,)

        self.ep = ((frm + to) // 2
                   if piece in 'Pp' and abs(to - frm) == 16 else None)

        if piece == 'K':
            self.castling -= {'K', 'Q'}
        elif piece == 'k':
            self.castling -= {'k', 'q'}
        for corner, right in ((63, 'K'), (56, 'Q'), (7, 'k'), (0, 'q')):
            if frm == corner or to == corner:
                self.castling.discard(right)

        self.halfmove = 0 if (piece in 'Pp' or captured != '.') else self.halfmove + 1
        if not white:
            self.fullmove += 1
        self.white_to_move = not self.white_to_move
        return undo

    def unmake(self, undo):
        frm, to, promo, captured, cap_sq, castling, ep, hm, fm, rook = undo
        b = self.squares
        piece = b[to]
        if promo:
            piece = 'P' if piece.isupper() else 'p'
        b[frm] = piece
        b[to] = '.'
        if captured != '.':
            b[cap_sq] = captured
        if rook:
            rf, rt = rook
            b[rf] = b[rt]
            b[rt] = '.'
        self.castling = castling
        self.ep = ep
        self.halfmove = hm
        self.fullmove = fm
        self.white_to_move = not self.white_to_move

    # -- serialisation ---------------------------------------------------

    @classmethod
    def from_fen(cls, text):
        placement, side, castle, ep, hm, fm = text.split()
        board = cls()
        squares = []
        for row in placement.split('/'):
            for ch in row:
                if ch.isdigit():
                    squares.extend('.' * int(ch))
                else:
                    squares.append(ch)
        if len(squares) != 64:
            raise ValueError("bad FEN placement: %r" % placement)
        board.squares = squares
        board.white_to_move = side == 'w'
        board.castling = set() if castle == '-' else set(castle)
        board.ep = None if ep == '-' else square_index(ep)
        board.halfmove = int(hm)
        board.fullmove = int(fm)
        return board

    def fen(self):
        rows = []
        for r in range(8):
            row, gap = '', 0
            for f in range(8):
                p = self.squares[r * 8 + f]
                if p == '.':
                    gap += 1
                else:
                    if gap:
                        row += str(gap)
                        gap = 0
                    row += p
            if gap:
                row += str(gap)
            rows.append(row)
        castle = ''.join(c for c in 'KQkq' if c in self.castling) or '-'
        return "%s %s %s %s %d %d" % (
            '/'.join(rows), 'w' if self.white_to_move else 'b', castle,
            square_name(self.ep) if self.ep is not None else '-',
            self.halfmove, self.fullmove)

    def has_mating_material(self):
        pieces = [p for p in self.squares if p not in '.Kk']
        if any(p.upper() in 'PRQ' for p in pieces):
            return True
        return len(pieces) > 1


# --------------------------------------------------------------------------
# Evaluation
# --------------------------------------------------------------------------

VALUES = {'P': 100, 'N': 320, 'B': 330, 'R': 500, 'Q': 900, 'K': 0}

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

KING_ENDGAME = (-50, -40, -30, -20, -20, -30, -40, -50,
                -30, -20, -10, 0, 0, -10, -20, -30,
                -30, -10, 20, 30, 30, 20, -10, -30,
                -30, -10, 30, 40, 40, 30, -10, -30,
                -30, -10, 30, 40, 40, 30, -10, -30,
                -30, -10, 20, 30, 30, 20, -10, -30,
                -30, -30, 0, 0, 0, 0, -30, -30,
                -50, -30, -30, -30, -30, -30, -30, -50)

MATE = 100000


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
    endgame = heavy < 1300

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
        score += 30
    if bishops[1] >= 2:
        score -= 30

    for side, sign in ((0, 1), (1, -1)):
        files = pawn_files[side]
        for f, count in enumerate(files):
            if count > 1:
                score -= sign * 15 * (count - 1)
            if count and not (f and files[f - 1]) and not (f < 7 and files[f + 1]):
                score -= sign * 12
    return score


# --------------------------------------------------------------------------
# Search
# --------------------------------------------------------------------------

class TimeUp(Exception):
    pass


class Engine:
    def __init__(self, depth=4, time_limit=3.0, blunder=0):
        self.depth = depth
        self.time_limit = time_limit
        self.blunder = blunder          # centipawn slack for weaker play
        self.nodes = 0
        self.deadline = 0.0

    def _tick(self):
        self.nodes += 1
        if not self.nodes & 2047 and time.time() > self.deadline:
            raise TimeUp

    def _order(self, board, moves, best_first=None):
        b = board.squares

        def score(mv):
            frm, to, promo = mv
            s = 0
            if mv == best_first:
                return 1_000_000
            victim = b[to]
            if victim != '.':
                s += 10 * VALUES[victim.upper()] - VALUES[b[frm].upper()]
            if promo:
                s += VALUES[promo]
            return s

        return sorted(moves, key=score, reverse=True)

    def quiesce(self, board, alpha, beta):
        self._tick()
        sign = 1 if board.white_to_move else -1
        stand = sign * evaluate(board)
        if stand >= beta:
            return beta
        alpha = max(alpha, stand)

        captures = [m for m in board.gen_pseudo()
                    if board.squares[m[1]] != '.' or m[2]]
        for mv in self._order(board, captures):
            undo = board.make(mv)
            if board.attacked(board.king_sq(not board.white_to_move),
                              board.white_to_move):
                board.unmake(undo)
                continue
            try:
                score = -self.quiesce(board, -beta, -alpha)
            finally:
                # TimeUp unwinds through here; the move must come off the
                # board either way or the caller inherits a corrupt position.
                board.unmake(undo)
            if score >= beta:
                return beta
            alpha = max(alpha, score)
        return alpha

    def negamax(self, board, depth, alpha, beta, ply):
        self._tick()
        if board.halfmove >= 100 or not board.has_mating_material():
            return 0
        if depth <= 0:
            return self.quiesce(board, alpha, beta)

        moves = board.legal_moves()
        if not moves:
            if board.in_check(board.white_to_move):
                return -MATE + ply
            return 0

        for mv in self._order(board, moves):
            undo = board.make(mv)
            try:
                score = -self.negamax(board, depth - 1, -beta, -alpha, ply + 1)
            finally:
                board.unmake(undo)
            if score >= beta:
                return beta
            alpha = max(alpha, score)
        return alpha

    def choose(self, board):
        """Iterative deepening; returns (move, score, depth_reached)."""
        self.nodes = 0
        self.deadline = time.time() + self.time_limit
        root = board.legal_moves()
        if not root:
            return None, 0, 0

        best, best_score, reached = root[0], 0, 0
        scored = [(m, 0) for m in root]

        for depth in range(1, self.depth + 1):
            try:
                alpha, results = -MATE * 2, []
                for mv in self._order(board, root, best_first=best):
                    undo = board.make(mv)
                    try:
                        score = -self.negamax(board, depth - 1,
                                              -MATE * 2, -alpha, 1)
                    finally:
                        board.unmake(undo)
                    results.append((mv, score))
                    if score > alpha:
                        alpha = score
                results.sort(key=lambda x: x[1], reverse=True)
                scored = results
                best, best_score, reached = results[0][0], results[0][1], depth
                if abs(best_score) > MATE - 100:
                    break
            except TimeUp:
                break

        if self.blunder:
            pool = [m for m, s in scored if s >= best_score - self.blunder]
            best = random.choice(pool)
            best_score = dict(scored)[best]
        return best, best_score, reached


# --------------------------------------------------------------------------
# Notation
# --------------------------------------------------------------------------

def move_to_san(board, mv, legal=None):
    frm, to, promo = mv
    piece = board.squares[frm]
    u = piece.upper()

    if u == 'K' and abs(to - frm) == 2:
        text = 'O-O' if to > frm else 'O-O-O'
    else:
        capture = board.squares[to] != '.' or (u == 'P' and to == board.ep)
        if u == 'P':
            text = (FILES[frm % 8] + 'x' if capture else '') + square_name(to)
            if promo:
                text += '=' + promo
        else:
            rivals = [m for m in (legal if legal is not None else board.legal_moves())
                      if m != mv and m[1] == to and board.squares[m[0]] == piece]
            hint = ''
            if rivals:
                if all(m[0] % 8 != frm % 8 for m in rivals):
                    hint = FILES[frm % 8]
                elif all(m[0] // 8 != frm // 8 for m in rivals):
                    hint = RANKS[frm // 8]
                else:
                    hint = square_name(frm)
            text = u + hint + ('x' if capture else '') + square_name(to)

    undo = board.make(mv)
    if board.in_check(board.white_to_move):
        text += '#' if not board.legal_moves() else '+'
    board.unmake(undo)
    return text


def parse_move(board, text, legal):
    """Accept coordinate notation or SAN. Returns a move or None."""
    raw = text.strip()
    if not raw:
        return None

    lower = raw.lower()
    if (len(lower) in (4, 5) and lower[0] in FILES and lower[1] in RANKS
            and lower[2] in FILES and lower[3] in RANKS):
        frm, to = square_index(lower[:2]), square_index(lower[2:4])
        promo = lower[4].upper() if len(lower) == 5 else None
        for m in legal:
            if m[0] == frm and m[1] == to and (m[2] == promo or promo is None
                                               and m[2] == 'Q'):
                return m
        return None

    want = raw.replace('0', 'O').rstrip('+#')
    for m in legal:
        if move_to_san(board, m, legal).rstrip('+#') == want:
            return m
    return None


# --------------------------------------------------------------------------
# Display
# --------------------------------------------------------------------------

GLYPHS = {'K': '\u2654', 'Q': '\u2655', 'R': '\u2656', 'B': '\u2657',
          'N': '\u2658', 'P': '\u2659', 'k': '\u265A', 'q': '\u265B',
          'r': '\u265C', 'b': '\u265D', 'n': '\u265E', 'p': '\u265F'}


def _unicode_ok():
    try:
        '\u2654'.encode(sys.stdout.encoding or 'ascii')
        return True
    except (UnicodeEncodeError, LookupError, TypeError):
        return False


USE_GLYPHS = _unicode_ok()


def render(board, flipped=False):
    rows = range(7, -1, -1) if flipped else range(8)
    files = range(7, -1, -1) if flipped else range(8)
    out = ["   +------------------------+"]
    for r in rows:
        cells = []
        for f in files:
            p = board.squares[r * 8 + f]
            if p == '.':
                cells.append('.' if (r + f) % 2 else ' ')
            else:
                cells.append(GLYPHS[p] if USE_GLYPHS else p)
        out.append(" %s | %s |" % (RANKS[r], '  '.join(cells)))
    out.append("   +------------------------+")
    out.append("     " + '  '.join(FILES[f] for f in files))
    return '\n'.join(out)


HELP = """
Moves      e2e4, g1f3, e7e8q     (coordinates, optional promotion piece)
           e4, Nf3, exd5, O-O    (algebraic notation)

Commands   board    redraw the position
           moves    list every legal move
           undo     take back your last move and the reply
           fen      print the FEN string
           flip     flip the board orientation
           new      restart the game
           help     show this text
           quit     exit
"""

LEVELS = {
    '1': ("Easy", Engine(depth=2, time_limit=0.4, blunder=90)),
    '2': ("Medium", Engine(depth=4, time_limit=1.5, blunder=25)),
    '3': ("Hard", Engine(depth=6, time_limit=4.0, blunder=0)),
    '4': ("Brutal", Engine(depth=8, time_limit=10.0, blunder=0)),
}


def ask(prompt, valid):
    while True:
        try:
            answer = input(prompt).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)
        if answer in valid:
            return answer
        print("  Please enter one of: %s" % ', '.join(valid))


def game_over(board, seen):
    """Return a result string, or None if the game continues."""
    if not board.legal_moves():
        if board.in_check(board.white_to_move):
            return "Checkmate -- %s wins." % ("Black" if board.white_to_move
                                              else "White")
        return "Stalemate -- draw."
    if board.halfmove >= 100:
        return "Draw by the fifty-move rule."
    if not board.has_mating_material():
        return "Draw -- insufficient material."
    if seen.get(board.key(), 0) >= 3:
        return "Draw by threefold repetition."
    return None


def main():
    print("\n  T E R M I N A L   C H E S S\n")

    while True:
        colour = ask("  Play as (w)hite or (b)lack? ", {'w', 'b'})
        human_white = colour == 'w'

        print("\n  1) Easy    2) Medium    3) Hard    4) Brutal")
        level = ask("  Difficulty? ", set(LEVELS))
        label, engine = LEVELS[level]
        print("\n  %s, you are %s. Type 'help' for commands.\n"
              % (label, "White" if human_white else "Black"))

        board = Board()
        flipped = not human_white
        seen = {board.key(): 1}
        undo_stack = []
        history = []

        print(render(board, flipped))

        while True:
            result = game_over(board, seen)
            if result:
                print("\n  %s\n" % result)
                break

            if board.white_to_move == human_white:
                legal = board.legal_moves()
                try:
                    raw = input("  %d%s > " % (board.fullmove,
                                               '.' if board.white_to_move
                                               else '...')).strip()
                except (EOFError, KeyboardInterrupt):
                    print("\n  Goodbye.\n")
                    return

                cmd = raw.lower()
                if cmd in ('quit', 'exit', 'q'):
                    print("  Goodbye.\n")
                    return
                if cmd in ('help', '?'):
                    print(HELP)
                    continue
                if cmd == 'board':
                    print(render(board, flipped))
                    continue
                if cmd == 'flip':
                    flipped = not flipped
                    print(render(board, flipped))
                    continue
                if cmd == 'fen':
                    print("  %s" % board.fen())
                    continue
                if cmd == 'moves':
                    names = sorted(move_to_san(board, m, legal) for m in legal)
                    print("  %d legal: %s" % (len(names), '  '.join(names)))
                    continue
                if cmd == 'new':
                    break
                if cmd == 'undo':
                    if len(undo_stack) < 2:
                        print("  Nothing to take back.")
                        continue
                    for _ in range(2):
                        seen[board.key()] -= 1
                        board.unmake(undo_stack.pop())
                        history.pop()
                    print(render(board, flipped))
                    continue

                mv = parse_move(board, raw, legal)
                if mv is None:
                    print("  Illegal or unrecognised move: %r "
                          "(try 'moves' for the list)" % raw)
                    continue

                san = move_to_san(board, mv, legal)
                undo_stack.append(board.make(mv))
                history.append(san)
                seen[board.key()] = seen.get(board.key(), 0) + 1
                print("  You play %s" % san)

            else:
                print("  Thinking...", end='', flush=True)
                started = time.time()
                mv, score, depth = engine.choose(board)
                elapsed = time.time() - started
                if mv is None:
                    continue

                san = move_to_san(board, mv)
                undo_stack.append(board.make(mv))
                history.append(san)
                seen[board.key()] = seen.get(board.key(), 0) + 1

                # `score` is from the mover's (computer's) point of view;
                # report it from White's, as is conventional.
                white_pov = score if not human_white else -score
                if abs(score) > MATE - 100:
                    verdict = "mate in %d" % ((MATE - abs(score) + 1) // 2)
                else:
                    verdict = "%+.2f" % (white_pov / 100.0)
                print("\r  Computer plays %-8s (depth %d, %s, %.1fs, %d nodes)"
                      % (san, depth, verdict, elapsed, engine.nodes))
                print(render(board, flipped))

                if board.in_check(board.white_to_move) and board.legal_moves():
                    print("  Check!")

        if history:
            print("  Moves: %s\n" % ' '.join(
                ("%d.%s" % (i // 2 + 1, m) if i % 2 == 0 else m)
                for i, m in enumerate(history)))
        if ask("  Play again? (y/n) ", {'y', 'n'}) == 'n':
            print("  Thanks for playing.\n")
            return
        print()


if __name__ == "__main__":
    main()

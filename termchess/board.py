"""Board state, make/unmake, and FEN serialisation.

make() returns an undo record that unmake() consumes, so the search never
copies the board -- it mutates one shared position and rewinds it. Every field
that make() touches must be captured in that record, or the search silently
operates on a position that never existed.
"""

from . import movegen
from .constants import START, square_index, square_name


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
        """Hashable identity of the position, for repetition detection."""
        return (''.join(self.squares), self.white_to_move,
                frozenset(self.castling), self.ep)

    def king_sq(self, white):
        return self.squares.index('K' if white else 'k')

    def in_check(self, white):
        return movegen.attacked(self, self.king_sq(white), not white)

    # -- move generation (delegates; see movegen) -------------------------

    def attacked(self, s, by_white):
        return movegen.attacked(self, s, by_white)

    def gen_pseudo(self):
        return movegen.pseudo_moves(self)

    def legal_moves(self):
        return movegen.legal_moves(self)

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
        """False only for the dead-drawn material configurations.

        A pawn, rook or queen can always mate. Otherwise a lone minor piece
        cannot, but two pieces of any kind are treated as sufficient.
        """
        pieces = [p for p in self.squares if p not in '.Kk']
        if any(p.upper() in 'PRQ' for p in pieces):
            return True
        return len(pieces) > 1

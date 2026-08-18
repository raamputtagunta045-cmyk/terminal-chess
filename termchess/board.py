"""Board state, make/unmake, and FEN serialisation.

make() returns an undo record that unmake() consumes, so the search never
copies the board -- it mutates one shared position and rewinds it. Every field
that make() touches must be captured in that record, or the search silently
operates on a position that never existed.
"""

from . import movegen
from .constants import (
    CASTLE_LOSS_BY_PIECE, CORNER_RIGHT, HEAVY_VALUE, IS_KING, IS_PRQ, START,
    ZOBRIST_CASTLING, ZOBRIST_EP_FILE, ZOBRIST_PIECE, ZOBRIST_SIDE,
    square_index, square_name,
)


class Board:
    """Full chess position with make/unmake for search.

    Four derived quantities are maintained incrementally rather than recomputed
    on demand, because every one of them used to be an O(64) scan sitting in the
    innermost search loop:

        heavy     non-pawn, non-king material (drives the endgame test)
        prq       count of pawns, rooks and queens (mating material)
        npieces   count of non-king pieces        (mating material)
        wk, bk    king squares

    Incremental state is a classic source of silent corruption, so recount()
    recomputes all of it from the squares and the integrity tests assert the
    two agree after every move.
    """

    def __init__(self):
        self.squares = list(START)
        self.white_to_move = True
        self.castling = {'K', 'Q', 'k', 'q'}
        self.ep = None
        self.halfmove = 0
        self.fullmove = 1
        self.recount()

    # -- derived state ---------------------------------------------------

    def recount(self):
        """Recompute every incrementally-maintained field from the squares."""
        self.heavy = 0
        self.prq = 0
        self.npieces = 0
        self.wk = self.bk = -1
        for s, p in enumerate(self.squares):
            if p == '.':
                continue
            if p == 'K':
                self.wk = s
                continue
            if p == 'k':
                self.bk = s
                continue
            self.npieces += 1
            self.heavy += HEAVY_VALUE[p]
            if IS_PRQ[p]:
                self.prq += 1
        self.hash = self.compute_hash()

    def compute_hash(self):
        """Zobrist key computed from scratch.

        make()/unmake() maintain self.hash incrementally; this is the
        independent definition they are checked against.
        """
        h = 0
        for s, p in enumerate(self.squares):
            if p != '.':
                h ^= ZOBRIST_PIECE[p][s]
        for right in self.castling:
            h ^= ZOBRIST_CASTLING[right]
        if self.ep is not None:
            h ^= ZOBRIST_EP_FILE[self.ep & 7]
        if not self.white_to_move:
            h ^= ZOBRIST_SIDE
        return h

    # -- queries ---------------------------------------------------------

    def key(self):
        """Hashable identity of the position, for repetition detection."""
        return (''.join(self.squares), self.white_to_move,
                frozenset(self.castling), self.ep)

    def king_sq(self, white):
        return self.wk if white else self.bk

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

        # The castling set is stored by reference, not copied. Rights are now
        # updated copy-on-write below, so the stored object is never mutated
        # and unmake can simply put the original back. Copying it here cost an
        # allocation on every make(), and the large majority of moves do not
        # touch castling rights at all.
        undo = (frm, to, promo, captured, cap_sq, self.castling,
                self.ep, self.halfmove, self.fullmove, None, self.hash)

        # Zobrist update. XOR out what stops being true, XOR in what starts
        # being true. The piece leaving its square and arriving at another are
        # separate terms, which is why a move is a handful of XORs rather than
        # a rescan of the board.
        h = self.hash ^ ZOBRIST_SIDE
        if self.ep is not None:
            h ^= ZOBRIST_EP_FILE[self.ep & 7]
        h ^= ZOBRIST_PIECE[piece][frm]
        if captured != '.':
            h ^= ZOBRIST_PIECE[captured][cap_sq]

        # Incremental material bookkeeping. A captured king is possible in the
        # pseudo-legal move list (the position is then illegal and the move is
        # discarded immediately), and it is deliberately not counted here --
        # its tracked square is unchanged by the capture and is restored by
        # unmake putting the king straight back where it stood.
        if captured != '.' and not IS_KING[captured]:
            self.npieces -= 1
            self.heavy -= HEAVY_VALUE[captured]
            if IS_PRQ[captured]:
                self.prq -= 1

        b[to] = promo.upper() if promo and white else (
            promo.lower() if promo else piece)
        b[frm] = '.'
        h ^= ZOBRIST_PIECE[b[to]][to]

        if promo:
            # A pawn (counted in prq) becomes something else; the piece count
            # is unchanged but its classification is not.
            self.prq -= 1
            self.heavy += HEAVY_VALUE[promo]
            if promo in 'RQ':
                self.prq += 1
        elif piece == 'K':
            self.wk = to
        elif piece == 'k':
            self.bk = to

        if piece in 'Kk' and abs(to - frm) == 2:
            if to > frm:
                rf, rt = frm + 3, frm + 1
            else:
                rf, rt = frm - 4, frm - 1
            b[rt] = b[rf]
            b[rf] = '.'
            h ^= ZOBRIST_PIECE[b[rt]][rf] ^ ZOBRIST_PIECE[b[rt]][rt]
            rook_move = (rf, rt)
            undo = undo[:9] + (rook_move, undo[10])

        self.ep = ((frm + to) // 2
                   if piece in 'Pp' and abs(to - frm) == 16 else None)
        if self.ep is not None:
            h ^= ZOBRIST_EP_FILE[self.ep & 7]

        rights = self.castling
        if rights:
            # Collect what this move could cost, then rebuild the set only if
            # it actually costs something the position still had.
            doomed = CASTLE_LOSS_BY_PIECE.get(piece)
            from_corner = CORNER_RIGHT.get(frm)
            to_corner = CORNER_RIGHT.get(to)
            if doomed or from_corner or to_corner:
                lost = set(doomed) if doomed else set()
                if from_corner:
                    lost.add(from_corner)
                if to_corner:
                    lost.add(to_corner)
                actually_lost = lost & rights
                if actually_lost:
                    self.castling = rights - actually_lost
                    for right in actually_lost:
                        h ^= ZOBRIST_CASTLING[right]

        self.halfmove = 0 if (piece in 'Pp' or captured != '.') else self.halfmove + 1
        if not white:
            self.fullmove += 1
        self.white_to_move = not self.white_to_move
        self.hash = h
        return undo

    def unmake(self, undo):
        (frm, to, promo, captured, cap_sq, castling, ep, hm, fm, rook,
         prev_hash) = undo
        b = self.squares
        piece = b[to]
        if promo:
            piece = 'P' if piece.isupper() else 'p'
        b[frm] = piece
        b[to] = '.'

        # Exactly the inverse of make()'s bookkeeping, in reverse order.
        if promo:
            self.heavy -= HEAVY_VALUE[promo]
            if promo in 'RQ':
                self.prq -= 1
            self.prq += 1                      # the pawn comes back
        elif piece == 'K':
            self.wk = frm
        elif piece == 'k':
            self.bk = frm

        if captured != '.':
            b[cap_sq] = captured
            if not IS_KING[captured]:
                self.npieces += 1
                self.heavy += HEAVY_VALUE[captured]
                if IS_PRQ[captured]:
                    self.prq += 1
        if rook:
            rf, rt = rook
            b[rf] = b[rt]
            b[rt] = '.'
        self.castling = castling
        self.ep = ep
        self.halfmove = hm
        self.fullmove = fm
        self.white_to_move = not self.white_to_move
        self.hash = prev_hash

    def make_null(self):
        """Pass the turn without moving, for null-move pruning.

        The idea being tested is: even if I do nothing, is my position
        still so good that the opponent cannot reach beta? Passing is not
        a legal chess move, which is exactly why the search must not use
        this while in check, or in an endgame bare enough for zugzwang --
        positions where having to move is itself the problem, so a free
        pass flatters wildly.
        """
        undo = (self.ep, self.halfmove, self.hash)
        h = self.hash ^ ZOBRIST_SIDE
        if self.ep is not None:
            h ^= ZOBRIST_EP_FILE[self.ep & 7]
        self.ep = None
        self.halfmove += 1
        self.white_to_move = not self.white_to_move
        self.hash = h
        return undo

    def unmake_null(self, undo):
        self.ep, self.halfmove, self.hash = undo
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
        board.recount()
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

        Answered from incrementally-maintained counts. It used to allocate a
        list of every non-king piece on every one of 40,000 search nodes.
        """
        return self.prq > 0 or self.npieces > 1

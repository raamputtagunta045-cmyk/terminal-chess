"""Standard algebraic notation: generation and parsing.

SAN is defined by what a *reader* needs to reconstruct the move, so generating
it requires knowing the other legal moves -- 'Nf3' is only valid if no other
knight can reach f3. That is why move_to_san takes the legal move list: it has
to look at the alternatives before it can name the move.
"""

from .constants import FILES, RANKS, square_index, square_name


def move_to_san(board, mv, legal=None):
    """Render a move in standard algebraic notation.

    `legal` is the move list for the current position; pass it when you already
    have one, since disambiguation otherwise has to regenerate it.
    """
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
            # Only pieces of the same type reaching the same square need a
            # disambiguating hint, and file is preferred over rank.
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

    # The check/mate suffix can only be known by playing the move.
    undo = board.make(mv)
    if board.in_check(board.white_to_move):
        text += '#' if not board.legal_moves() else '+'
    board.unmake(undo)
    return text


def parse_move(board, text, legal):
    """Accept coordinate notation or SAN. Returns a move or None.

    Nothing is trusted: the result is always one of the moves in `legal`, so an
    unparseable or illegal input can only ever yield None.
    """
    raw = text.strip()
    if not raw:
        return None

    lower = raw.lower()
    if (len(lower) in (4, 5) and lower[0] in FILES and lower[1] in RANKS
            and lower[2] in FILES and lower[3] in RANKS):
        frm, to = square_index(lower[:2]), square_index(lower[2:4])
        promo = lower[4].upper() if len(lower) == 5 else None
        for m in legal:
            # Bare coordinates onto the last rank mean a queen promotion.
            if m[0] == frm and m[1] == to and (m[2] == promo or promo is None
                                               and m[2] == 'Q'):
                return m
        return None

    # SAN: generate each legal move's name and compare. Slower than parsing the
    # string, but it can never disagree with what the program prints.
    want = raw.replace('0', 'O').rstrip('+#')
    for m in legal:
        if move_to_san(board, m, legal).rstrip('+#') == want:
            return m
    return None

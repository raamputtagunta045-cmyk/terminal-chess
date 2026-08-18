"""Shared test fixtures and helpers.

Its presence at the repository root also puts the root on sys.path, so suites
living under tests/ can `import chess_game` the same way the top-level
test_chess_game.py does.
"""

import pytest

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

# A corpus wide enough that a refactor cannot quietly break one feature: each
# entry exercises something different (castling rights, en passant, promotion
# races, endgame king activity, heavy tactics).
CORPUS = {
    "startpos": START_FEN,
    "italian": "r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/2N2N2/PPPP1PPP/R1BQK2R w KQkq - 4 5",
    "kiwipete": "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
    "promotion": "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1",
    "endgame": "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1",
    "en_passant": "rnbqkbnr/ppp1p1pp/8/3pPp2/8/8/PPPP1PPP/RNBQKBNR w KQkq f6 0 3",
    "rook_endgame": "8/8/8/4k3/8/8/4P3/4K3 w - - 0 40",
    "castling_only": "r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1",
}

CORPUS_IDS = sorted(CORPUS)
CORPUS_FENS = [CORPUS[name] for name in CORPUS_IDS]


@pytest.fixture(params=CORPUS_IDS)
def corpus_fen(request):
    """Every FEN in the corpus, one per test invocation."""
    return CORPUS[request.param]


def mirror_fen(fen):
    """Reflect a position: swap colours and flip the board top to bottom.

    The result is the same position with the sides exchanged, so a correct,
    colour-symmetric evaluation must return exactly the negated score. Any
    asymmetry -- a bonus applied to one colour only, a table indexed the wrong
    way -- shows up immediately as a mismatch.
    """
    placement, side, castling, ep, halfmove, fullmove = fen.split()

    rows = placement.split('/')
    flipped = '/'.join(row.swapcase() for row in reversed(rows))

    side = 'b' if side == 'w' else 'w'

    if castling == '-':
        swapped_castling = '-'
    else:
        swapped = castling.swapcase()
        swapped_castling = ''.join(c for c in 'KQkq' if c in swapped)

    if ep == '-':
        mirrored_ep = '-'
    else:
        mirrored_ep = ep[0] + str(9 - int(ep[1]))

    return ' '.join([flipped, side, swapped_castling, mirrored_ep,
                     halfmove, fullmove])


def board_state(board):
    """Everything that must survive a make/unmake round trip.

    Uses getattr for the Zobrist key so this helper keeps working before the
    hash exists and automatically gains teeth once it does.
    """
    return {
        "squares": list(board.squares),
        "white_to_move": board.white_to_move,
        "castling": set(board.castling),
        "ep": board.ep,
        "halfmove": board.halfmove,
        "fullmove": board.fullmove,
        "hash": getattr(board, "hash", None),
    }


def describe(board, move):
    """Readable assertion context: which move, in which position."""
    return "move %r in %s" % (move, board.fen())

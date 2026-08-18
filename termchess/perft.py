"""Perft -- the authoritative move-generation check.

Perft counts the leaf nodes of the move tree to a given depth. Because the
reference counts for standard positions are known exactly, any disagreement
means move generation is wrong: a missing en-passant capture, a castle through
check, a promotion not offered. Unit tests cannot catch those the way this can,
which is why any change to move generation must keep perft green.
"""

from . import movegen
from .board import Board
from .notation import move_to_san

# Standard reference positions and their published node counts, indexed by
# depth (element 0 is depth 0, which is always 1).
REFERENCE = {
    "startpos": (
        "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        [1, 20, 400, 8902, 197281, 4865609],
    ),
    "kiwipete": (
        "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
        [1, 48, 2039, 97862, 4085603],
    ),
    "endgame": (
        "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1",
        [1, 14, 191, 2812, 43238, 674624],
    ),
    "promotion": (
        "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1",
        [1, 6, 264, 9467, 422333],
    ),
    "mirrored": (
        "rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8",
        [1, 44, 1486, 62379, 2103487],
    ),
}


def perft(board, depth):
    """Count leaf nodes of the legal move tree at `depth`."""
    if depth == 0:
        return 1
    total = 0
    for mv in movegen.legal_moves(board):
        undo = board.make(mv)
        total += perft(board, depth - 1)
        board.unmake(undo)
    return total


def divide(board, depth):
    """Per-move perft breakdown -- the standard way to localise a discrepancy.

    Compare against a known-good engine's divide output for the same position:
    the move whose subtree count differs points straight at the bug.
    """
    if depth < 1:
        raise ValueError("divide needs depth >= 1")
    out = []
    legal = movegen.legal_moves(board)
    for mv in legal:
        san = move_to_san(board, mv, legal)
        undo = board.make(mv)
        out.append((san, perft(board, depth - 1)))
        board.unmake(undo)
    out.sort()
    return out


def check(name, depth):
    """Run one reference position and return (actual, expected)."""
    fen, counts = REFERENCE[name]
    if depth >= len(counts):
        raise ValueError("no reference count for %s depth %d" % (name, depth))
    return perft(Board.from_fen(fen), depth), counts[depth]

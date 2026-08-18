"""Extended perft -- deeper move-generation verification.

test_chess_game.py already checks the shallow counts on every run. This suite
goes deeper and wider, against the published reference numbers, and is marked
slow so the fast gate stays fast. Depth is where move generation bugs actually
live: an en-passant capture that exposes the king, a castle through an attacked
square, a promotion generated only for queens. None of those show up at depth 2.

The reference counts are not the engine's own output. They are the published
values for these standard positions, so agreeing with them is evidence rather
than a tautology.
"""

import pytest

from termchess import Board
from termchess.perft import REFERENCE, check, divide, perft


def _cases(max_depth):
    """Every (position, depth) pair with a published count, up to max_depth."""
    out = []
    for name, (_fen, counts) in sorted(REFERENCE.items()):
        for depth in range(1, min(max_depth, len(counts) - 1) + 1):
            out.append((name, depth))
    return out


class TestReferencePositions:
    @pytest.mark.parametrize("name,depth", _cases(3))
    def test_shallow(self, name, depth):
        actual, expected = check(name, depth)
        assert actual == expected

    @pytest.mark.slow
    @pytest.mark.parametrize("name,depth", _cases(4))
    def test_to_depth_four(self, name, depth):
        actual, expected = check(name, depth)
        assert actual == expected

    @pytest.mark.slow
    @pytest.mark.parametrize("name", ["startpos", "endgame"])
    def test_to_depth_five(self, name):
        actual, expected = check(name, 5)
        assert actual == expected


class TestDivide:
    """divide() is the tool used to localise a perft mismatch."""

    def test_divide_sums_to_perft(self):
        board = Board()
        breakdown = divide(board, 3)
        assert sum(count for _, count in breakdown) == perft(Board(), 3)

    def test_divide_lists_every_legal_move(self):
        breakdown = divide(Board(), 1)
        assert len(breakdown) == 20
        assert all(count == 1 for _, count in breakdown)

    def test_divide_leaves_the_board_untouched(self):
        board = Board.from_fen(REFERENCE["kiwipete"][0])
        before = board.fen()
        divide(board, 2)
        assert board.fen() == before

    def test_divide_rejects_depth_zero(self):
        with pytest.raises(ValueError):
            divide(Board(), 0)


class TestPerftProperties:
    def test_depth_zero_is_one(self):
        """The empty move sequence is itself a node."""
        assert perft(Board(), 0) == 1

    def test_perft_does_not_disturb_the_position(self):
        board = Board.from_fen(REFERENCE["promotion"][0])
        before = board.fen()
        perft(board, 3)
        assert board.fen() == before

    def test_unknown_depth_is_rejected(self):
        with pytest.raises(ValueError):
            check("startpos", 99)

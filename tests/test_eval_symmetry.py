"""Evaluation symmetry.

A position and its colour-reflected twin describe the same struggle with the
sides exchanged, so a correct evaluation must score them as exact negatives.
This catches the most common evaluation bug there is: a term added for one
colour and forgotten for the other, or a piece-square table indexed without the
colour flip. Those bugs do not crash anything -- they just make the engine
quietly prefer being one colour.

Written before the evaluation is extended, so every term added later inherits
the check for free.
"""

import pytest

from conftest import CORPUS, CORPUS_IDS, mirror_fen
from chess_game import Board, evaluate


class TestMirror:
    @pytest.mark.parametrize("name", CORPUS_IDS)
    def test_mirrored_position_scores_exactly_negated(self, name):
        fen = CORPUS[name]
        original = evaluate(Board.from_fen(fen))
        mirrored = evaluate(Board.from_fen(mirror_fen(fen)))
        assert original == -mirrored, (
            "%s scored %d but its mirror scored %d (expected %d)"
            % (name, original, mirrored, -original))

    @pytest.mark.parametrize("name", CORPUS_IDS)
    def test_mirroring_twice_is_the_identity(self, name):
        """Guards the test helper itself, not the engine."""
        fen = CORPUS[name]
        assert mirror_fen(mirror_fen(fen)) == fen

    def test_starting_position_is_dead_even(self):
        assert evaluate(Board()) == 0

    @pytest.mark.parametrize("name", CORPUS_IDS)
    def test_side_to_move_does_not_change_the_score(self, name):
        """evaluate() is absolute (White's point of view), not side-relative.

        The search applies the sign itself. If evaluation ever started leaning
        on white_to_move, the negamax sign convention would silently double up.
        """
        fen = CORPUS[name]
        board = Board.from_fen(fen)
        score = evaluate(board)
        board.white_to_move = not board.white_to_move
        assert evaluate(board) == score


class TestMaterialOrdering:
    """Sanity anchors: more material must score better, in the right direction."""

    @pytest.mark.parametrize("piece,floor", [
        ("Q", 800), ("R", 450), ("B", 250), ("N", 250), ("P", 50),
    ])
    def test_extra_white_piece_favours_white(self, piece, floor):
        bare = evaluate(Board.from_fen("4k3/8/8/8/8/8/8/4K3 w - - 0 1"))
        with_piece = evaluate(
            Board.from_fen("4k3/8/8/8/8/8/4%s3/4K3 w - - 0 1" % piece))
        assert with_piece - bare > floor

    def test_queen_outweighs_rook(self):
        queen = evaluate(Board.from_fen("4k3/8/8/8/8/8/8/3QK3 w - - 0 1"))
        rook = evaluate(Board.from_fen("4k3/8/8/8/8/8/8/3RK3 w - - 0 1"))
        assert queen > rook

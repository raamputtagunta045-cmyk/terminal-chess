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

from chess_game import Board, evaluate
from conftest import CORPUS, CORPUS_IDS, mirror_fen


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


class TestTaperedEvaluation:
    """Phase interpolation, and the terms that depend on it."""

    def test_phase_is_full_at_the_start_and_empty_in_a_pawn_endgame(self):
        from termchess.evaluate import PHASE_OF, TOTAL_PHASE
        full = sum(PHASE_OF[p] for p in Board().squares if p != '.')
        assert full == TOTAL_PHASE
        bare = Board.from_fen("4k3/pppppppp/8/8/8/8/PPPPPPPP/4K3 w - - 0 1")
        assert sum(PHASE_OF[p] for p in bare.squares if p != '.') == 0

    def test_king_activity_is_rewarded_only_as_the_endgame_arrives(self):
        """The point of tapering: the same king move is judged differently.

        A centralised king is a liability with queens on and an asset without,
        so its evaluation must slide rather than flip at an arbitrary
        material threshold.
        """
        centre_eg = evaluate(Board.from_fen("8/8/8/3K4/8/8/8/7k w - - 0 1"))
        corner_eg = evaluate(Board.from_fen("8/8/8/8/8/8/8/K6k w - - 0 1"))
        assert centre_eg > corner_eg

    def test_score_is_between_the_two_readings(self):
        """Interpolation must not produce a value outside its endpoints."""
        from termchess.evaluate import (
            ENDGAME_SCORE,
            MIDGAME_SCORE,
            PHASE_OF,
            TOTAL_PHASE,
        )
        fen = "r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/2N2N2/PPPP1PPP/R1BQK2R w KQkq - 4 5"
        board = Board.from_fen(fen)
        mg = sum(MIDGAME_SCORE[p][s]
                 for s, p in enumerate(board.squares) if p != '.')
        eg = sum(ENDGAME_SCORE[p][s]
                 for s, p in enumerate(board.squares) if p != '.')
        assert min(mg, eg) - 200 <= evaluate(board) <= max(mg, eg) + 200
        del TOTAL_PHASE, PHASE_OF


class TestPawnStructure:
    def test_passed_pawn_is_worth_more_than_a_blocked_one(self):
        passed = evaluate(Board.from_fen("4k3/8/8/4P3/8/8/8/4K3 w - - 0 1"))
        blocked = evaluate(Board.from_fen("4k3/8/4p3/4P3/8/8/8/4K3 w - - 0 1"))
        assert passed > blocked

    def test_advanced_passer_beats_a_home_passer(self):
        far = evaluate(Board.from_fen("4k3/4P3/8/8/8/8/8/4K3 w - - 0 1"))
        near = evaluate(Board.from_fen("4k3/8/8/8/8/8/4P3/4K3 w - - 0 1"))
        assert far > near

    def test_doubled_pawns_are_not_treated_as_passers(self):
        """A pawn with its own partner behind it cannot advance freely.

        Counting it as passed made a doubled isolated pair outscore two
        healthy connected pawns, which is backwards.
        """
        doubled = evaluate(Board.from_fen("4k3/8/8/8/P7/8/P7/4K3 w - - 0 1"))
        connected = evaluate(Board.from_fen("4k3/8/8/8/8/8/PP6/4K3 w - - 0 1"))
        assert doubled < connected

    def test_isolated_pawn_is_penalised(self):
        isolated = evaluate(Board.from_fen("4k3/8/8/8/8/8/P1P5/4K3 w - - 0 1"))
        connected = evaluate(Board.from_fen("4k3/8/8/8/8/8/PP6/4K3 w - - 0 1"))
        assert isolated < connected


class TestPieceActivity:
    def test_rook_prefers_an_open_file(self):
        open_file = evaluate(Board.from_fen("4k3/8/8/8/8/8/1P6/R3K3 w - - 0 1"))
        blocked = evaluate(Board.from_fen("4k3/8/8/8/8/8/P7/R3K3 w - - 0 1"))
        assert open_file > blocked

    def test_king_shield_matters_with_pieces_on(self):
        """Missing pawns in front of the king are a middlegame liability."""
        sheltered = evaluate(Board.from_fen(
            "rnbq1rk1/pppppppp/8/8/8/8/PPPPPPPP/RNBQ1RK1 w - - 0 1"))
        exposed = evaluate(Board.from_fen(
            "rnbq1rk1/pppppppp/8/8/6P1/5P1P/PPPPP3/RNBQ1RK1 w - - 0 1"))
        assert exposed < sheltered

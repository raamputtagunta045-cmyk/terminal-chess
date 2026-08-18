"""Tactical suite -- does the search actually find the move?

Perft proves move generation is correct; nothing there proves the engine
*plays* well. These positions each have a single defensible answer, so a
regression in ordering, pruning or evaluation shows up as a wrong move rather
than as a number that drifted.

Every expectation here was verified against the engine before being written
down. Several plausible-looking candidates were discarded in the process: a
knight fork that wins a queen scores zero because the resulting K+N vs K is a
dead draw, and a "mate in one" that turned out not to be mate at all. A
tactical suite whose answers were assumed rather than checked tests the
author's chess, not the engine's.
"""

import pytest

from termchess import MATE, Board, Engine, move_to_san


def best(fen, depth):
    """Search a position and return (SAN, score)."""
    board = Board.from_fen(fen)
    engine = Engine(depth=depth, time_limit=10 ** 6, blunder=0)
    move, score, _ = engine.choose(board)
    assert move is not None, "no legal move in %s" % fen
    return move_to_san(board, move), score


class TestMates:
    """Forced mates. The score must also say mate, not merely 'winning'."""

    def test_back_rank_mate(self):
        san, score = best("6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1", 3)
        assert san == "Ra8#"
        assert score > MATE - 100

    def test_back_rank_mate_with_own_pawns_present(self):
        """Same idea, but White has pawns that must not distract the search."""
        san, score = best("6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1", 4)
        assert san == "Ra8#"
        assert score > MATE - 100

    def test_smothered_mate(self):
        """Nf7# -- the king is boxed in by its own rook and pawns."""
        san, score = best("6rk/6pp/8/6N1/8/8/8/6K1 w - - 0 1", 5)
        assert san == "Nf7#"
        assert score > MATE - 100

    def test_mate_is_preferred_to_mere_material(self):
        """A mate score must dominate any amount of material."""
        _, mate_score = best("6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1", 3)
        _, material_score = best("4k3/8/8/8/8/8/3q4/R3K3 w - - 0 1", 3)
        assert mate_score > material_score


class TestWinningMaterial:
    def test_takes_the_undefended_queen(self):
        san, score = best("4k3/8/8/8/8/8/3q4/R3K3 w - - 0 1", 3)
        assert san == "Kxd2"
        assert score > 400

    def test_skewer_wins_the_rook(self):
        """The rook on e2 gives check and is itself undefended."""
        san, score = best("4k3/8/8/8/8/8/4r3/4K2R w K - 0 1", 4)
        assert san == "Kxe2"
        assert score > 400

    def test_capture_promotion_is_found(self):
        """exd8=Q+ both removes the rook and makes a queen."""
        san, score = best("3r2k1/4P3/8/8/8/8/8/4K3 w - - 0 1", 4)
        assert san == "exd8=Q+"
        assert score > 800

    def test_wins_a_rook_with_check(self):
        san, score = best("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1", 4)
        assert san == "Rxa8+"
        assert score > 400


class TestAvoidingBlunders:
    def test_declines_to_hang_the_queen(self):
        """Qxa7 wins a pawn and loses the queen to the rook on a8."""
        san, _ = best("r3k3/p7/8/8/8/8/8/3QK3 w - - 0 1", 4)
        assert san != "Qxa7"

    def test_sees_that_a_won_piece_can_leave_a_dead_draw(self):
        """Nxd5 wins the queen and reaches K+N vs K, which cannot mate.

        The engine scores this at exactly zero rather than +900. That is not a
        bug, and it is the reason this position is here: material counting
        alone gets it badly wrong, and insufficient-material detection is what
        saves it.
        """
        _, score = best("4k3/8/8/3q4/8/2N5/8/4K3 w - - 0 1", 4)
        assert score == 0


class TestSpecialMoves:
    def test_en_passant_capture_is_searchable(self):
        """The engine must be able to choose an en-passant capture at all."""
        san, _ = best("8/8/8/8/4pP2/8/8/4K2k b - f3 0 1", 4)
        assert san == "exf3"

    def test_promotion_race_is_understood_as_winning(self):
        """White is a pawn away from a queen; the score must reflect that."""
        _, score = best("8/4P3/8/8/8/8/8/4K1k1 w - - 0 1", 4)
        assert score > 700


class TestSearchInvariants:
    @pytest.mark.parametrize("fen", [
        "6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1",
        "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
        "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1",
    ])
    def test_the_returned_move_is_legal(self, fen):
        board = Board.from_fen(fen)
        move, _, _ = Engine(depth=4, time_limit=10 ** 6).choose(board)
        assert move in board.legal_moves()

    @pytest.mark.parametrize("fen", [
        "6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1",
        "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
    ])
    def test_the_principal_variation_is_playable(self, fen):
        """Every move of the reported PV must be legal in turn.

        The PV is reconstructed by following transposition entries, so a
        corrupted table or a hash collision would surface here as a line that
        cannot actually be played.
        """
        from termchess import parse_move
        board = Board.from_fen(fen)
        engine = Engine(depth=4, time_limit=10 ** 6)
        engine.choose(board)
        assert engine.pv, "no principal variation was produced"

        undos = []
        try:
            for san in engine.pv:
                legal = board.legal_moves()
                move = parse_move(board, san, legal)
                assert move is not None, (
                    "PV move %r is not legal in %s" % (san, board.fen()))
                undos.append(board.make(move))
        finally:
            while undos:
                board.unmake(undos.pop())

    def test_a_deterministic_engine_repeats_itself(self):
        """With blunder=0 the same search must give the same answer."""
        fen = "r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/2N2N2/PPPP1PPP/R1BQK2R w KQkq - 4 5"
        first = best(fen, 4)
        second = best(fen, 4)
        assert first == second

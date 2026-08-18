"""Make/unmake integrity -- the invariant the whole search rests on.

The search never copies the board; it mutates one shared position and relies on
unmake() putting every last field back. If that is even slightly wrong the
engine plays moves from a position that does not exist, and the failure surfaces
far away from its cause. These tests pin the invariant down directly.

test_chess_game.py already checks the basic round trip. This suite goes further:
full state (not just __dict__ equality), recursive depth, and a seeded random
walk that reaches positions no hand-written case would think to try.
"""

import random

import pytest

from conftest import CORPUS, CORPUS_IDS, board_state, describe
from chess_game import Board


def _assert_equal(before, after, context):
    assert before == after, context


def _walk(board, depth):
    """Make and unmake every legal move recursively, checking restoration."""
    if depth == 0:
        return
    for move in board.legal_moves():
        before = board_state(board)
        undo = board.make(move)
        _walk(board, depth - 1)
        board.unmake(undo)
        _assert_equal(before, board_state(board), describe(board, move))


class TestMakeUnmake:
    @pytest.mark.parametrize("name", CORPUS_IDS)
    def test_every_field_restored(self, name):
        """One ply: every tracked field must come back identical."""
        board = Board.from_fen(CORPUS[name])
        for move in board.legal_moves():
            before = board_state(board)
            undo = board.make(move)
            board.unmake(undo)
            assert board_state(board) == before, describe(board, move)

    @pytest.mark.parametrize("name", CORPUS_IDS)
    def test_restored_three_plies_deep(self, name):
        """Nested make/unmake, as the search actually does it."""
        _walk(Board.from_fen(CORPUS[name]), 3)

    @pytest.mark.parametrize("name", CORPUS_IDS)
    def test_fen_survives_round_trip(self, name):
        """FEN is the human-visible projection of the state; it must be stable."""
        board = Board.from_fen(CORPUS[name])
        for move in board.legal_moves():
            before = board.fen()
            undo = board.make(move)
            board.unmake(undo)
            assert board.fen() == before, describe(board, move)

    def test_random_game_unwinds_completely(self):
        """Play a long seeded game, then unmake all of it back to the start.

        Unmaking in reverse order is the strongest form of the invariant: any
        field that leaks state across a move shows up as a mismatch at the end.
        """
        rng = random.Random(20260817)
        board = Board()
        start = board_state(board)

        undos = []
        for _ in range(120):
            legal = board.legal_moves()
            if not legal:
                break
            undos.append(board.make(rng.choice(legal)))

        assert len(undos) > 40, "game ended too early to be a useful test"

        while undos:
            board.unmake(undos.pop())
        assert board_state(board) == start

    @pytest.mark.parametrize("name", CORPUS_IDS)
    def test_castling_rights_never_gained(self, name):
        """Rights are monotonically lost; a move must never create one."""
        board = Board.from_fen(CORPUS[name])
        rights = set(board.castling)
        for move in board.legal_moves():
            undo = board.make(move)
            assert board.castling <= rights, describe(board, move)
            board.unmake(undo)


class TestKingIntegrity:
    """Exactly one king per side, always -- a cheap canary for movegen bugs."""

    @pytest.mark.parametrize("name", CORPUS_IDS)
    def test_kings_survive_every_move(self, name):
        board = Board.from_fen(CORPUS[name])
        for move in board.legal_moves():
            undo = board.make(move)
            assert board.squares.count("K") == 1, describe(board, move)
            assert board.squares.count("k") == 1, describe(board, move)
            board.unmake(undo)

    @pytest.mark.parametrize("name", CORPUS_IDS)
    def test_king_is_never_capturable(self, name):
        """After any legal move, the mover's king must not be en prise.

        This is the definition of legality, checked independently of the
        generator that produced the move.
        """
        board = Board.from_fen(CORPUS[name])
        mover_is_white = board.white_to_move
        for move in board.legal_moves():
            undo = board.make(move)
            assert not board.attacked(board.king_sq(mover_is_white),
                                      not mover_is_white), describe(board, move)
            board.unmake(undo)

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

from chess_game import Board, square_index
from conftest import CORPUS, CORPUS_IDS, board_state, describe


def find(board, san):
    """Locate a legal move by its SAN name."""
    from chess_game import move_to_san
    legal = board.legal_moves()
    for m in legal:
        if move_to_san(board, m, legal) == san:
            return m
    raise AssertionError("no legal move %r in %s" % (san, board.fen()))


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


class TestIncrementalState:
    """Incrementally-maintained counters must never drift from the truth.

    heavy, prq, npieces and the king squares are updated by deltas inside
    make()/unmake() instead of being recomputed. That is a large speed win and
    a classic source of silent corruption: nothing crashes when a counter goes
    stale, the engine just starts evaluating positions with the wrong endgame
    table or claiming a drawn position has mating material.

    recount() recomputes all of it from the squares, so comparing the two is a
    direct test of the invariant.
    """

    @staticmethod
    def _snapshot(board):
        return (board.heavy, board.prq, board.npieces, board.wk, board.bk)

    @staticmethod
    def _truth(board):
        import copy
        probe = copy.deepcopy(board)
        probe.recount()
        return TestIncrementalState._snapshot(probe)

    @pytest.mark.parametrize("name", CORPUS_IDS)
    def test_counters_match_after_every_move(self, name):
        board = Board.from_fen(CORPUS[name])
        for move in board.legal_moves():
            undo = board.make(move)
            assert self._snapshot(board) == self._truth(board), \
                "drifted after %s" % (move,)
            board.unmake(undo)
            assert self._snapshot(board) == self._truth(board), \
                "drifted unmaking %s" % (move,)

    def test_counters_survive_a_long_random_game(self):
        """Promotions and captures are where the deltas are easiest to get wrong."""
        rng = random.Random(99)
        board = Board()
        for _ in range(140):
            legal = board.legal_moves()
            if not legal:
                break
            board.make(rng.choice(legal))
            assert self._snapshot(board) == self._truth(board), board.fen()

    def test_promotion_updates_material(self):
        """A pawn becoming a queen adds heavy material and stays 'PRQ'."""
        board = Board.from_fen("8/4P3/8/8/8/8/8/4K1k1 w - - 0 1")
        before = board.heavy
        board.make(find(board, "e8=Q"))
        assert board.heavy == before + 900
        assert self._snapshot(board) == self._truth(board)

    def test_underpromotion_to_knight_leaves_prq(self):
        """Knight is not P, R or Q, so the mating-material class changes."""
        board = Board.from_fen("8/4P3/8/8/8/8/8/4K1k1 w - - 0 1")
        before = board.prq
        board.make(find(board, "e8=N"))
        assert board.prq == before - 1
        assert self._snapshot(board) == self._truth(board)

    def test_king_square_tracks_castling(self):
        board = Board.from_fen("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
        undo = board.make(find(board, "O-O"))
        assert board.wk == square_index("g1")
        assert board.king_sq(True) == square_index("g1")
        board.unmake(undo)
        assert board.wk == square_index("e1")

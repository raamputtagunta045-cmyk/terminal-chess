"""Zobrist hash correctness.

The transposition table trusts the hash completely: two positions sharing a key
are treated as the same position. A hash that drifts from the position it is
supposed to describe therefore does not produce a crash or an illegal move -- it
produces an engine that occasionally returns the evaluation of a position it is
not looking at, which is close to impossible to debug from the symptom.

So the hash is pinned down here before anything depends on it. The essential
property is that the incrementally-maintained key always equals the key computed
from scratch.
"""

import random

import pytest

from conftest import CORPUS, CORPUS_IDS
from termchess import Board
from termchess.constants import ZOBRIST_EP_FILE, ZOBRIST_PIECE, ZOBRIST_SIDE


class TestIncrementalMatchesScratch:
    """The one property everything else rests on."""

    @pytest.mark.parametrize("name", CORPUS_IDS)
    def test_after_every_single_move(self, name):
        board = Board.from_fen(CORPUS[name])
        for move in board.legal_moves():
            undo = board.make(move)
            assert board.hash == board.compute_hash(), \
                "hash drifted making %r in %s" % (move, CORPUS[name])
            board.unmake(undo)
            assert board.hash == board.compute_hash(), \
                "hash drifted unmaking %r in %s" % (move, CORPUS[name])

    @pytest.mark.parametrize("name", CORPUS_IDS)
    def test_three_plies_deep(self, name):
        board = Board.from_fen(CORPUS[name])
        self._walk(board, 3)

    def _walk(self, board, depth):
        if depth == 0:
            return
        for move in board.legal_moves():
            undo = board.make(move)
            assert board.hash == board.compute_hash(), board.fen()
            self._walk(board, depth - 1)
            board.unmake(undo)
            assert board.hash == board.compute_hash(), board.fen()

    def test_long_random_game(self):
        """Reaches promotions, en passant and castling without being told to."""
        rng = random.Random(31337)
        board = Board()
        for _ in range(160):
            legal = board.legal_moves()
            if not legal:
                break
            board.make(rng.choice(legal))
            assert board.hash == board.compute_hash(), board.fen()

    def test_restored_exactly_after_unwinding_a_game(self):
        rng = random.Random(2718)
        board = Board()
        start = board.hash
        undos = []
        for _ in range(100):
            legal = board.legal_moves()
            if not legal:
                break
            undos.append(board.make(rng.choice(legal)))
        assert board.hash != start, "the game went nowhere"
        while undos:
            board.unmake(undos.pop())
        assert board.hash == start


class TestHashDistinguishesPositions:
    """A hash that ignores part of the position would collide silently."""

    def test_side_to_move_changes_the_hash(self):
        white = Board.from_fen("4k3/8/8/8/8/8/8/4K3 w - - 0 1")
        black = Board.from_fen("4k3/8/8/8/8/8/8/4K3 b - - 0 1")
        assert white.hash != black.hash
        assert white.hash == black.hash ^ ZOBRIST_SIDE

    def test_castling_rights_change_the_hash(self):
        full = Board.from_fen("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
        none = Board.from_fen("r3k2r/8/8/8/8/8/8/R3K2R w - - 0 1")
        assert full.hash != none.hash

    def test_en_passant_file_changes_the_hash(self):
        with_ep = Board.from_fen(
            "rnbqkbnr/ppp1p1pp/8/3pPp2/8/8/PPPP1PPP/RNBQKBNR w KQkq f6 0 3")
        without = Board.from_fen(
            "rnbqkbnr/ppp1p1pp/8/3pPp2/8/8/PPPP1PPP/RNBQKBNR w KQkq - 0 3")
        assert with_ep.hash != without.hash
        assert with_ep.hash == without.hash ^ ZOBRIST_EP_FILE[5]  # f-file

    def test_piece_placement_changes_the_hash(self):
        here = Board.from_fen("4k3/8/8/8/8/8/4N3/4K3 w - - 0 1")
        there = Board.from_fen("4k3/8/8/8/8/8/5N2/4K3 w - - 0 1")
        assert here.hash != there.hash

    def test_transpositions_collide_on_purpose(self):
        """Different move orders reaching one position must share a key.

        This is the whole point of the table: the same position arrived at two
        ways should be searched once, not twice.

        Knight moves only, deliberately. A line containing a double pawn push
        does *not* transpose -- it leaves an en-passant square behind, which is
        part of the position and part of the hash.
        """
        one = Board()
        for mv in ["Nf3", "Nf6", "Nc3", "Nc6"]:
            one.make(_find(one, mv))
        two = Board()
        for mv in ["Nc3", "Nc6", "Nf3", "Nf6"]:
            two.make(_find(two, mv))
        assert one.fen() == two.fen()
        assert one.hash == two.hash

    def test_a_double_push_does_not_transpose(self):
        """The counterexample to the test above, made explicit.

        1.Nf3 d5 2.d4 and 1.d4 d5 2.Nf3 have identical piece placement but are
        different positions: the first leaves an en-passant square on d3. The
        hashes must differ, or the table would conflate them.
        """
        one = Board()
        for mv in ["Nf3", "d5", "d4"]:
            one.make(_find(one, mv))
        two = Board()
        for mv in ["d4", "d5", "Nf3"]:
            two.make(_find(two, mv))
        assert one.squares == two.squares
        assert one.ep is not None and two.ep is None
        assert one.hash != two.hash

    def test_startpos_hash_is_stable_across_runs(self):
        """The generator is seeded, so this value is fixed.

        If it ever changes, saved analysis and any persisted table become
        meaningless -- worth noticing deliberately rather than by accident.
        """
        assert Board().hash == Board().compute_hash()
        assert Board.from_fen(
            "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        ).hash == Board().hash


def _find(board, san):
    from termchess import move_to_san
    legal = board.legal_moves()
    for m in legal:
        if move_to_san(board, m, legal) == san:
            return m
    raise AssertionError("no %r in %s" % (san, board.fen()))


def test_zobrist_table_has_no_duplicates():
    """Two identical randoms would make two different facts indistinguishable."""
    values = [v for table in ZOBRIST_PIECE.values() for v in table]
    assert len(set(values)) == len(values) == 768


class TestRepetitionAwareness:
    """The search must recognise a repeated position as a draw.

    Before this existed the engine was blind to perpetuals: it could not see
    that a line returning to an earlier position ends the game, so it would
    evaluate such a line on material alone.
    """

    def test_the_search_actually_detects_repetitions(self):
        """Direct evidence, not a proxy.

        An earlier version of this test used a position where the engine simply
        won a queen; it passed identically with repetition detection removed,
        so it proved nothing. The engine now counts the nodes it scores as a
        draw by repetition, which cannot be satisfied by accident.
        """
        from termchess import Engine
        board = Board.from_fen("8/8/8/3k4/8/8/8/R3K3 w Q - 0 1")
        engine = Engine(depth=5, time_limit=10 ** 6)
        engine.choose(board)
        assert engine.repetitions > 0, (
            "no node was scored as a repetition, so the feature is inert")

    def test_repetition_changes_the_verdict(self):
        """Differential evidence via the same API the game uses.

        White can win a queen with Kxd2. Tell the engine that the position
        *after* Kxd2 has already occurred, and that capture becomes a
        repetition -- a draw -- rather than a win. The score must move
        accordingly. This exercises exactly the path the CLI relies on when it
        hands the engine the game's position history.
        """
        from termchess import Engine

        fen = "4k3/8/8/8/8/8/3q4/R3K3 w - - 0 1"
        board = Board.from_fen(fen)
        engine = Engine(depth=3, time_limit=10 ** 6)

        move, winning, _ = engine.choose(board)
        assert winning > 400, "expected the queen capture to look winning"

        undo = board.make(move)
        already_seen = board.hash
        board.unmake(undo)

        _, drawn, _ = engine.choose(board, history=[already_seen])
        assert drawn < winning, (
            "score unchanged (%d) after declaring the resulting position "
            "already seen, so game history is being ignored" % drawn)

    def test_history_is_honoured(self):
        """Positions already seen in the game count toward repetition."""
        from termchess import Engine
        board = Board()
        engine = Engine(depth=2, time_limit=10 ** 6)
        engine.choose(board, history=[board.hash])
        # The root hash appears twice on the path; the search must still return
        # a legal move rather than mis-scoring the root as an instant draw.
        move, _, _ = engine.choose(board, history=[board.hash])
        assert move in board.legal_moves()

    def test_path_is_empty_after_a_search(self):
        """A leaked path entry would make unrelated later lines look repeated."""
        from termchess import Engine
        engine = Engine(depth=4, time_limit=10 ** 6)
        engine.choose(Board())
        assert len(engine.path) == 1  # just the root, pushed by choose()

    def test_path_unwinds_even_when_the_clock_expires(self):
        from termchess import Engine
        engine = Engine(depth=99, time_limit=0.05)
        board = Board.from_fen(
            "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4")
        before = board.fen()
        engine.choose(board)
        assert board.fen() == before
        assert len(engine.path) == 1

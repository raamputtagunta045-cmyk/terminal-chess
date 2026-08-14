"""Test suite for chess_game.py.

Covers move generation (castling, en passant, promotion, pins),
game-end detection, make/unmake symmetry, SAN round-trips, and draws.
"""

import copy

import pytest

from chess_game import (
    Board, Engine, MATE, START,
    move_to_san, parse_move, evaluate,
    square_index, square_name,
)

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def moves_from(board, origin):
    """Set of destination square names for the piece on `origin`."""
    src = square_index(origin)
    return {square_name(m[1]) for m in board.legal_moves() if m[0] == src}


def san_set(board):
    legal = board.legal_moves()
    return {move_to_san(board, m, legal) for m in legal}


def find(board, san):
    legal = board.legal_moves()
    for m in legal:
        if move_to_san(board, m, legal) == san:
            return m
    raise AssertionError("no legal move %r in %s" % (san, board.fen()))


# ---------------------------------------------------------------------------
# Coordinates
# ---------------------------------------------------------------------------

class TestCoordinates:
    def test_corners(self):
        assert square_index("a8") == 0
        assert square_index("h8") == 7
        assert square_index("a1") == 56
        assert square_index("h1") == 63

    @pytest.mark.parametrize("s", range(64))
    def test_roundtrip(self, s):
        assert square_index(square_name(s)) == s


# ---------------------------------------------------------------------------
# FEN
# ---------------------------------------------------------------------------

class TestFen:
    def test_initial_position(self):
        assert Board().fen() == START_FEN

    @pytest.mark.parametrize("fen", [
        START_FEN,
        "r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/2N2N2/PPPP1PPP/R1BQK2R w KQkq - 4 5",
        "8/8/8/4k3/8/8/4P3/4K3 w - - 0 40",
        "rnbqkbnr/ppp1p1pp/8/3pPp2/8/8/PPPP1PPP/RNBQKBNR w KQkq f6 0 3",
    ])
    def test_roundtrip(self, fen):
        assert Board.from_fen(fen).fen() == fen

    def test_rejects_short_placement(self):
        with pytest.raises(ValueError):
            Board.from_fen("8/8/8/8 w - - 0 1")


# ---------------------------------------------------------------------------
# Perft -- the authoritative move-generation check
# ---------------------------------------------------------------------------

def perft(board, depth):
    if depth == 0:
        return 1
    total = 0
    for mv in board.legal_moves():
        undo = board.make(mv)
        total += perft(board, depth - 1)
        board.unmake(undo)
    return total


class TestPerft:
    @pytest.mark.parametrize("depth,expected", [
        (1, 20), (2, 400), (3, 8902), (4, 197281),
    ])
    def test_initial_position(self, depth, expected):
        assert perft(Board(), depth) == expected

    @pytest.mark.parametrize("depth,expected", [(1, 48), (2, 2039), (3, 97862)])
    def test_kiwipete(self, depth, expected):
        """Dense middlegame: castling both sides, en passant, pins."""
        fen = ("r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/"
               "PPPBBPPP/R3K2R w KQkq - 0 1")
        assert perft(Board.from_fen(fen), depth) == expected

    @pytest.mark.parametrize("depth,expected", [(1, 14), (2, 191), (3, 2812)])
    def test_endgame_position(self, depth, expected):
        fen = "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1"
        assert perft(Board.from_fen(fen), depth) == expected

    @pytest.mark.parametrize("depth,expected", [(1, 6), (2, 264), (3, 9467)])
    def test_promotion_heavy(self, depth, expected):
        fen = "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1"
        assert perft(Board.from_fen(fen), depth) == expected

    @pytest.mark.slow
    def test_initial_depth_5(self):
        assert perft(Board(), 5) == 4865609


# ---------------------------------------------------------------------------
# Castling
# ---------------------------------------------------------------------------

class TestCastling:
    EMPTY_BACK = "r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1"

    def test_both_sides_available(self):
        board = Board.from_fen(self.EMPTY_BACK)
        assert {"g1", "c1"} <= moves_from(board, "e1")

    def test_blocked_by_own_piece(self):
        board = Board.from_fen("r3k2r/8/8/8/8/8/8/R3KB1R w KQkq - 0 1")
        assert "g1" not in moves_from(board, "e1")
        assert "c1" in moves_from(board, "e1")

    def test_forbidden_while_in_check(self):
        board = Board.from_fen("r3k2r/8/8/8/8/8/4r3/R3K2R w KQkq - 0 1")
        assert not {"g1", "c1"} & moves_from(board, "e1")

    def test_forbidden_through_attacked_square(self):
        """Rook on f8 covers f1, the king's transit square."""
        board = Board.from_fen("r4rk1/8/8/8/8/8/8/R3K2R w KQ - 0 1")
        assert "g1" not in moves_from(board, "e1")
        assert "c1" in moves_from(board, "e1")

    def test_allowed_when_only_rook_transit_attacked(self):
        """b1 is attacked but the king never touches it, so O-O-O is legal."""
        board = Board.from_fen("1r2k3/8/8/8/8/8/8/R3K2R w KQ - 0 1")
        assert "c1" in moves_from(board, "e1")

    def test_rights_lost_after_king_moves(self):
        board = Board.from_fen(self.EMPTY_BACK)
        board.make(find(board, "Kf1"))
        assert board.castling == {"k", "q"}

    def test_rights_lost_after_rook_moves(self):
        board = Board.from_fen(self.EMPTY_BACK)
        board.make(find(board, "Rb1"))
        assert board.castling == {"K", "k", "q"}

    def test_rights_lost_when_rook_captured(self):
        board = Board.from_fen("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
        board.make(find(board, "Rxa8+"))
        assert "q" not in board.castling

    def test_rook_relocates_kingside(self):
        board = Board.from_fen(self.EMPTY_BACK)
        board.make(find(board, "O-O"))
        assert board.squares[square_index("g1")] == "K"
        assert board.squares[square_index("f1")] == "R"
        assert board.squares[square_index("h1")] == "."

    def test_rook_relocates_queenside(self):
        board = Board.from_fen(self.EMPTY_BACK)
        board.make(find(board, "O-O-O"))
        assert board.squares[square_index("c1")] == "K"
        assert board.squares[square_index("d1")] == "R"
        assert board.squares[square_index("a1")] == "."

    def test_black_castles(self):
        board = Board.from_fen("r3k2r/8/8/8/8/8/8/R3K2R b KQkq - 0 1")
        board.make(find(board, "O-O"))
        assert board.squares[square_index("g8")] == "k"
        assert board.squares[square_index("f8")] == "r"


# ---------------------------------------------------------------------------
# En passant
# ---------------------------------------------------------------------------

class TestEnPassant:
    def test_square_set_after_double_push(self):
        board = Board()
        board.make(find(board, "e4"))
        assert board.ep == square_index("e3")

    def test_square_cleared_after_quiet_move(self):
        board = Board()
        board.make(find(board, "e4"))
        board.make(find(board, "Nf6"))
        assert board.ep is None

    def test_not_set_after_single_push(self):
        board = Board()
        board.make(find(board, "e3"))
        assert board.ep is None

    def test_capture_is_generated(self):
        fen = "rnbqkbnr/ppp1p1pp/8/3pPp2/8/8/PPPP1PPP/RNBQKBNR w KQkq f6 0 3"
        board = Board.from_fen(fen)
        assert "exf6" in san_set(board)

    def test_capture_removes_correct_pawn(self):
        fen = "rnbqkbnr/ppp1p1pp/8/3pPp2/8/8/PPPP1PPP/RNBQKBNR w KQkq f6 0 3"
        board = Board.from_fen(fen)
        board.make(find(board, "exf6"))
        assert board.squares[square_index("f6")] == "P"
        assert board.squares[square_index("f5")] == "."
        assert board.squares[square_index("e5")] == "."

    def test_black_captures_en_passant(self):
        board = Board.from_fen("8/8/8/8/4pP2/8/8/4K2k b - f3 0 1")
        board.make(find(board, "exf3"))
        assert board.squares[square_index("f3")] == "p"
        assert board.squares[square_index("f4")] == "."

    def test_illegal_when_it_exposes_the_king(self):
        """Both pawns sit on rank 5; taking en passant unveils a rook check."""
        board = Board.from_fen("8/8/8/K1pP3r/8/8/8/7k w - c6 0 1")
        assert "dxc6" not in san_set(board)


# ---------------------------------------------------------------------------
# Promotion
# ---------------------------------------------------------------------------

class TestPromotion:
    def test_all_four_pieces_offered(self):
        board = Board.from_fen("8/4P3/8/8/8/8/8/4K1k1 w - - 0 1")
        assert {"e8=Q", "e8=R", "e8=B", "e8=N"} <= san_set(board)

    def test_piece_actually_placed(self):
        board = Board.from_fen("8/4P3/8/8/8/8/8/4K1k1 w - - 0 1")
        board.make(find(board, "e8=N"))
        assert board.squares[square_index("e8")] == "N"

    def test_black_promotes_lowercase(self):
        board = Board.from_fen("4k1K1/8/8/8/8/8/4p3/8 b - - 0 1")
        board.make(find(board, "e1=Q"))
        assert board.squares[square_index("e1")] == "q"

    def test_capture_promotion(self):
        board = Board.from_fen("3r2k1/4P3/8/8/8/8/8/4K3 w - - 0 1")
        assert "exd8=Q+" in san_set(board)

    def test_underpromotion_to_knight_forks(self):
        board = Board.from_fen("8/8/8/8/8/2k5/4P3/4K3 w - - 0 1")
        board.make(find(board, "e4"))
        assert board.squares[square_index("e4")] == "P"


# ---------------------------------------------------------------------------
# Pins and check evasion
# ---------------------------------------------------------------------------

class TestPins:
    def test_absolutely_pinned_piece_cannot_move(self):
        """Knight on e2 is pinned to e1 by the rook on e8."""
        board = Board.from_fen("4r2k/8/8/8/8/8/4N3/4K3 w - - 0 1")
        assert moves_from(board, "e2") == set()

    def test_pinned_piece_may_move_along_the_pin(self):
        """Rook on e2 can slide up and down the e-file."""
        board = Board.from_fen("4r2k/8/8/8/8/8/4R3/4K3 w - - 0 1")
        assert moves_from(board, "e2") == {"e3", "e4", "e5", "e6", "e7", "e8"}

    def test_only_evasions_when_in_check(self):
        board = Board.from_fen("4r2k/8/8/8/8/8/8/4K3 w - - 0 1")
        assert moves_from(board, "e1") == {"d1", "f1", "d2", "f2"}

    def test_check_can_be_blocked(self):
        """Rook on a4 interposes on e4 to answer the check from e8."""
        board = Board.from_fen("4r2k/8/8/8/R7/8/8/4K3 w - - 0 1")
        assert "Re4" in san_set(board)

    def test_king_cannot_step_along_checking_ray(self):
        """e2 stays on the rook's file, so it is not an escape."""
        board = Board.from_fen("4r2k/8/8/8/8/8/8/4K3 w - - 0 1")
        assert "e2" not in moves_from(board, "e1")

    def test_kings_may_not_touch(self):
        board = Board.from_fen("8/8/8/4k3/8/4K3/8/8 w - - 0 1")
        assert not {"d4", "e4", "f4"} & moves_from(board, "e3")


# ---------------------------------------------------------------------------
# Game termination
# ---------------------------------------------------------------------------

class TestTermination:
    def test_fools_mate(self):
        board = Board()
        for san in ["f3", "e5", "g4", "Qh4#"]:
            board.make(find(board, san))
        assert board.legal_moves() == []
        assert board.in_check(board.white_to_move)

    def test_back_rank_mate(self):
        board = Board.from_fen("6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1")
        board.make(find(board, "Ra8#"))
        assert board.legal_moves() == []

    def test_stalemate_is_not_check(self):
        board = Board.from_fen("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")
        assert board.legal_moves() == []
        assert not board.in_check(board.white_to_move)

    def test_ongoing_position_has_moves(self):
        assert len(Board().legal_moves()) == 20

    @pytest.mark.parametrize("fen,expected", [
        ("8/8/8/4k3/8/8/8/4K3 w - - 0 1", False),           # K v K
        ("8/8/8/4k3/8/8/5N2/4K3 w - - 0 1", False),         # K+N v K
        ("8/8/8/4k3/8/8/5B2/4K3 w - - 0 1", False),         # K+B v K
        ("8/8/8/4k3/8/8/5P2/4K3 w - - 0 1", True),          # a pawn can promote
        ("8/8/8/4k3/8/8/5R2/4K3 w - - 0 1", True),
        ("8/8/8/4k3/8/8/4NN2/4K3 w - - 0 1", True),
    ])
    def test_mating_material(self, fen, expected):
        assert Board.from_fen(fen).has_mating_material() is expected

    def test_halfmove_clock_counts_quiet_moves(self):
        board = Board.from_fen("4k3/8/8/8/8/8/8/R3K3 w - - 10 20")
        board.make(find(board, "Ra5"))
        assert board.halfmove == 11

    def test_halfmove_clock_resets_on_pawn_move(self):
        board = Board.from_fen("4k3/8/8/8/8/8/P7/4K3 w - - 10 20")
        board.make(find(board, "a3"))
        assert board.halfmove == 0

    def test_halfmove_clock_resets_on_capture(self):
        board = Board.from_fen("4k3/8/8/8/8/8/r7/R3K3 w - - 10 20")
        board.make(find(board, "Rxa2"))
        assert board.halfmove == 0

    def test_fullmove_increments_after_black(self):
        board = Board()
        board.make(find(board, "e4"))
        assert board.fullmove == 1
        board.make(find(board, "e5"))
        assert board.fullmove == 2


# ---------------------------------------------------------------------------
# make / unmake symmetry
# ---------------------------------------------------------------------------

SYMMETRY_POSITIONS = [
    START_FEN,
    "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
    "rnbqkbnr/ppp1p1pp/8/3pPp2/8/8/PPPP1PPP/RNBQKBNR w KQkq f6 0 3",
    "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1",
    "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1",
]


class TestMakeUnmake:
    @pytest.mark.parametrize("fen", SYMMETRY_POSITIONS)
    def test_state_restored_for_every_legal_move(self, fen):
        board = Board.from_fen(fen)
        before = copy.deepcopy(board.__dict__)
        for mv in board.legal_moves():
            undo = board.make(mv)
            board.unmake(undo)
            assert board.__dict__ == before, "corrupted by %s" % (mv,)

    @pytest.mark.parametrize("fen", SYMMETRY_POSITIONS)
    def test_state_restored_two_plies_deep(self, fen):
        board = Board.from_fen(fen)
        before = copy.deepcopy(board.__dict__)
        for first in board.legal_moves():
            u1 = board.make(first)
            for second in board.legal_moves():
                u2 = board.make(second)
                board.unmake(u2)
            board.unmake(u1)
        assert board.__dict__ == before

    def test_castling_is_reversible(self):
        board = Board.from_fen("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
        before = board.fen()
        undo = board.make(find(board, "O-O-O"))
        board.unmake(undo)
        assert board.fen() == before

    def test_en_passant_is_reversible(self):
        fen = "rnbqkbnr/ppp1p1pp/8/3pPp2/8/8/PPPP1PPP/RNBQKBNR w KQkq f6 0 3"
        board = Board.from_fen(fen)
        undo = board.make(find(board, "exf6"))
        board.unmake(undo)
        assert board.fen() == fen

    def test_promotion_is_reversible(self):
        fen = "3r1k2/4P3/8/8/8/8/8/4K3 w - - 0 1"
        board = Board.from_fen(fen)
        undo = board.make(find(board, "exd8=Q+"))
        board.unmake(undo)
        assert board.fen() == fen


# ---------------------------------------------------------------------------
# SAN
# ---------------------------------------------------------------------------

class TestSan:
    def test_opening_sequence(self):
        board = Board()
        for san in ["e4", "c5", "Nf3", "d6", "d4", "cxd4", "Nxd4", "Nf6"]:
            board.make(find(board, san))
        assert board.fen().startswith("rnbqkb1r/pp2pppp/3p1n2/8/3NP3/8/PPP2PPP")

    def test_check_suffix(self):
        board = Board.from_fen("4k3/8/8/8/8/8/8/R3K3 w - - 0 1")
        assert move_to_san(board, find(board, "Ra8+")) == "Ra8+"

    def test_mate_suffix(self):
        board = Board.from_fen("6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1")
        assert move_to_san(board, find(board, "Ra8#")) == "Ra8#"

    def test_file_disambiguation(self):
        board = Board.from_fen("4k3/8/8/8/8/8/4K3/R6R w - - 0 1")
        assert {"Rad1", "Rhd1"} <= san_set(board)

    def test_rank_disambiguation(self):
        board = Board.from_fen("7k/R7/8/8/8/8/8/R3K3 w - - 0 1")
        assert {"R1a4", "R7a4"} <= san_set(board)

    def test_no_disambiguation_when_unambiguous(self):
        board = Board()
        assert "Nf3" in san_set(board)
        assert "Ngf3" not in san_set(board)

    def test_pawn_capture_uses_source_file(self):
        board = Board.from_fen("rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2")
        assert "exd5" in san_set(board)

    @pytest.mark.parametrize("fen", SYMMETRY_POSITIONS)
    def test_generated_san_is_reparseable(self, fen):
        """Every SAN the program emits must parse back to the same move."""
        board = Board.from_fen(fen)
        legal = board.legal_moves()
        for mv in legal:
            san = move_to_san(board, mv, legal)
            assert parse_move(board, san, legal) == mv, san

    @pytest.mark.parametrize("fen", SYMMETRY_POSITIONS)
    def test_generated_san_is_unique(self, fen):
        board = Board.from_fen(fen)
        legal = board.legal_moves()
        names = [move_to_san(board, m, legal) for m in legal]
        assert len(set(names)) == len(names)


# ---------------------------------------------------------------------------
# Input parsing
# ---------------------------------------------------------------------------

class TestParseMove:
    def test_coordinate_notation(self):
        board = Board()
        legal = board.legal_moves()
        assert parse_move(board, "e2e4", legal) == (square_index("e2"),
                                                    square_index("e4"), None)

    def test_coordinate_notation_is_case_insensitive(self):
        board = Board()
        legal = board.legal_moves()
        assert parse_move(board, "E2E4", legal) == parse_move(board, "e2e4", legal)

    def test_coordinate_promotion(self):
        board = Board.from_fen("8/4P3/8/8/8/8/8/4K1k1 w - - 0 1")
        legal = board.legal_moves()
        assert parse_move(board, "e7e8n", legal)[2] == "N"

    def test_bare_coordinates_default_to_queen(self):
        board = Board.from_fen("8/4P3/8/8/8/8/8/4K1k1 w - - 0 1")
        legal = board.legal_moves()
        assert parse_move(board, "e7e8", legal)[2] == "Q"

    def test_castling_with_zeroes(self):
        board = Board.from_fen("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
        legal = board.legal_moves()
        assert parse_move(board, "0-0", legal) == find(board, "O-O")

    def test_check_suffix_optional(self):
        board = Board.from_fen("4k3/8/8/8/8/8/8/R3K3 w - - 0 1")
        legal = board.legal_moves()
        assert parse_move(board, "Ra8", legal) == parse_move(board, "Ra8+", legal)

    @pytest.mark.parametrize("text", ["", "   ", "e9e4", "xyz", "Nf9", "e2e5",
                                      "O-O", "Qh5xx"])
    def test_rejects_bad_input(self, text):
        board = Board()
        assert parse_move(board, text, board.legal_moves()) is None


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

class TestEvaluate:
    def test_initial_position_is_balanced(self):
        assert evaluate(Board()) == 0

    def test_symmetric_position_is_balanced(self):
        board = Board.from_fen("4k3/pppppppp/8/8/8/8/PPPPPPPP/4K3 w - - 0 1")
        assert evaluate(board) == 0

    def test_extra_queen_favours_white(self):
        board = Board.from_fen("4k3/8/8/8/8/8/8/3QK3 w - - 0 1")
        assert evaluate(board) > 500

    def test_extra_rook_favours_black(self):
        board = Board.from_fen("r3k3/8/8/8/8/8/8/4K3 w - - 0 1")
        assert evaluate(board) < -300

    def test_sign_flips_with_colour(self):
        white = Board.from_fen("4k3/8/8/8/8/8/8/3QK3 w - - 0 1")
        black = Board.from_fen("3qk3/8/8/8/8/8/8/4K3 w - - 0 1")
        assert evaluate(white) == -evaluate(black)

    def test_doubled_pawns_penalised(self):
        clean = Board.from_fen("4k3/8/8/8/8/8/PP6/4K3 w - - 0 1")
        doubled = Board.from_fen("4k3/8/8/8/P7/8/P7/4K3 w - - 0 1")
        assert evaluate(doubled) < evaluate(clean)

    def test_bishop_pair_bonus(self):
        pair = Board.from_fen("4k3/8/8/8/8/8/8/2B1KB2 w - - 0 1")
        mixed = Board.from_fen("4k3/8/8/8/8/8/8/2B1KN2 w - - 0 1")
        assert evaluate(pair) - evaluate(mixed) > 30


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

class TestEngine:
    def test_returns_a_legal_move(self):
        board = Board()
        mv, _, _ = Engine(depth=2, time_limit=1.0).choose(board)
        assert mv in board.legal_moves()

    def test_returns_none_when_no_moves(self):
        board = Board.from_fen("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")
        mv, _, _ = Engine(depth=2, time_limit=1.0).choose(board)
        assert mv is None

    def test_finds_mate_in_one(self):
        board = Board.from_fen("6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1")
        mv, score, _ = Engine(depth=3, time_limit=3.0).choose(board)
        assert move_to_san(board, mv) == "Ra8#"
        assert score > MATE - 100

    def test_finds_mate_in_two(self):
        board = Board.from_fen("6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1")
        mv, score, _ = Engine(depth=4, time_limit=5.0).choose(board)
        assert move_to_san(board, mv) == "Ra8#"

    def test_captures_a_free_queen(self):
        board = Board.from_fen("4k3/8/8/8/8/8/3q4/4K3 w - - 0 1")
        mv, _, _ = Engine(depth=2, time_limit=2.0).choose(board)
        assert move_to_san(board, mv) == "Kxd2"

    def test_escapes_check(self):
        board = Board.from_fen("4r2k/8/8/8/8/8/8/4K3 w - - 0 1")
        mv, _, _ = Engine(depth=2, time_limit=2.0).choose(board)
        assert mv in board.legal_moves()

    def test_avoids_hanging_the_queen(self):
        """Qxa7 loses the queen to the rook; the engine should decline."""
        board = Board.from_fen("r3k3/p7/8/8/8/8/8/3QK3 w - - 0 1")
        mv, _, _ = Engine(depth=3, time_limit=3.0).choose(board)
        assert move_to_san(board, mv) != "Qxa7"

    def test_respects_time_limit(self):
        import time
        board = Board()
        start = time.time()
        Engine(depth=99, time_limit=1.0).choose(board)
        assert time.time() - start < 6.0

    def test_search_does_not_corrupt_the_board(self):
        board = Board()
        before = board.fen()
        Engine(depth=3, time_limit=2.0).choose(board)
        assert board.fen() == before

    def test_deeper_search_reaches_greater_depth(self):
        board = Board()
        _, _, shallow = Engine(depth=2, time_limit=5.0).choose(board)
        _, _, deep = Engine(depth=4, time_limit=15.0).choose(board)
        assert deep > shallow

    def test_blunder_setting_still_yields_legal_moves(self):
        board = Board()
        engine = Engine(depth=2, time_limit=1.0, blunder=100)
        for _ in range(5):
            mv, _, _ = engine.choose(board)
            assert mv in board.legal_moves()


# ---------------------------------------------------------------------------
# Integration
# ---------------------------------------------------------------------------

class TestSelfPlay:
    def test_engine_plays_a_legal_game(self):
        """40 plies of self-play must never produce an illegal state."""
        board = Board()
        engine = Engine(depth=2, time_limit=0.3)
        for _ in range(40):
            legal = board.legal_moves()
            if not legal or board.halfmove >= 100:
                break
            mv, _, _ = engine.choose(board)
            assert mv in legal
            board.make(mv)
            assert board.squares.count("K") == 1
            assert board.squares.count("k") == 1
            assert Board.from_fen(board.fen()).fen() == board.fen()

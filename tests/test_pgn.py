"""PGN import, export and round-tripping.

The property that matters is convergence: exporting a game, reading it back and
exporting again must produce the same text. That is stronger than "the parser
accepts our own output", because it also pins down the parts a sloppy
implementation quietly drops -- the result token, a non-standard start
position, the move numbering when a game begins on Black's turn.

Input is parsed leniently and output written strictly, so the tests come in two
halves: awkward real-world input that must be accepted, and canonical output
that must be exact.
"""

import pytest

from termchess import Board
from termchess.pgn import (
    RESULTS,
    canonical_moves,
    export_pgn,
    load_pgn,
    parse_pgn,
    replay,
)

OPENING = ["e4", "e5", "Nf3", "Nc6", "Bb5", "a6"]


class TestExport:
    def test_seven_tag_roster_is_present_and_ordered(self):
        text = export_pgn(OPENING)
        header = [line for line in text.splitlines() if line.startswith("[")]
        keys = [line.split()[0][1:] for line in header]
        assert keys[:7] == ["Event", "Site", "Date", "Round",
                            "White", "Black", "Result"]

    def test_movetext_is_numbered_from_one(self):
        text = export_pgn(["e4", "e5", "Nf3"])
        assert "1. e4 e5 2. Nf3" in text

    def test_result_token_ends_the_movetext(self):
        text = export_pgn(["e4"], result="1-0")
        assert text.rstrip().endswith("1-0")

    def test_player_names_are_recorded(self):
        text = export_pgn(OPENING, tags={"White": "Alice", "Black": "Bob"})
        assert '[White "Alice"]' in text
        assert '[Black "Bob"]' in text

    def test_a_bad_result_is_rejected(self):
        with pytest.raises(ValueError):
            export_pgn(["e4"], result="won")

    def test_standard_start_emits_no_fen_tag(self):
        """A FEN tag on a normal game is noise, and some readers dislike it."""
        assert "FEN" not in export_pgn(OPENING, start_fen=Board().fen())

    def test_custom_start_emits_setup_and_fen(self):
        fen = "4k3/8/8/8/8/8/4P3/4K3 w - - 0 40"
        text = export_pgn(["e4"], start_fen=fen)
        assert '[SetUp "1"]' in text
        assert '[FEN "%s"]' % fen in text

    def test_numbering_starts_from_the_real_move_number(self):
        """A game resumed mid-play must not restart the count at 1."""
        fen = "4k3/8/8/8/8/8/4P3/4K3 w - - 0 40"
        assert "40. e4" in export_pgn(["e4"], start_fen=fen)

    def test_black_to_move_uses_the_ellipsis_form(self):
        fen = "4k3/4p3/8/8/8/8/8/4K3 b - - 0 12"
        text = export_pgn(["e5"], start_fen=fen)
        assert "12... e5" in text


class TestParse:
    def test_tags_and_moves_are_recovered(self):
        text = export_pgn(OPENING, tags={"White": "Alice"}, result="0-1")
        tags, moves, result = parse_pgn(text)
        assert tags["White"] == "Alice"
        assert moves == OPENING
        assert result == "0-1"

    def test_brace_comments_are_ignored(self):
        _, moves, _ = parse_pgn("1. e4 {a fine move} e5 2. Nf3 *")
        assert moves == ["e4", "e5", "Nf3"]

    def test_semicolon_comments_are_ignored(self):
        _, moves, _ = parse_pgn(
            "1. e4 e5 ; the rest of this line is a note\n2. Nf3 *")
        assert moves == ["e4", "e5", "Nf3"]

    def test_variations_are_ignored_including_nested_ones(self):
        _, moves, _ = parse_pgn("1. e4 e5 (1... c5 (1... e6) 2. Nf3) 2. Nf3 *")
        assert moves == ["e4", "e5", "Nf3"]

    def test_numeric_annotation_glyphs_are_ignored(self):
        _, moves, _ = parse_pgn("1. e4 $1 e5 $2 2. Nf3 $14 *")
        assert moves == ["e4", "e5", "Nf3"]

    def test_black_ellipsis_numbering_is_ignored(self):
        _, moves, _ = parse_pgn("1. e4 1... e5 2. Nf3 *")
        assert moves == ["e4", "e5", "Nf3"]

    def test_result_falls_back_to_the_tag(self):
        _, _, result = parse_pgn('[Result "1-0"]\n\n1. e4 e5')
        assert result == "1-0"

    def test_result_defaults_to_unfinished(self):
        _, _, result = parse_pgn("1. e4 e5")
        assert result == "*"


class TestRoundTrip:
    def test_export_parse_export_converges(self):
        first = export_pgn(OPENING, tags={"White": "Alice", "Black": "Bob"},
                           result="1-0")
        tags, moves, result = parse_pgn(first)
        second = export_pgn(moves, tags=tags, result=result)
        assert first == second

    def test_round_trip_preserves_a_custom_start_position(self):
        fen = "r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1"
        first = export_pgn(["O-O", "O-O-O"], start_fen=fen, result="1/2-1/2")
        tags, moves, result = parse_pgn(first)
        second = export_pgn(moves, tags=tags, start_fen=tags["FEN"],
                            result=result)
        assert first == second

    @pytest.mark.parametrize("result", RESULTS)
    def test_every_result_survives(self, result):
        text = export_pgn(["e4"], result=result)
        _, _, parsed = parse_pgn(text)
        assert parsed == result

    def test_sloppy_input_is_normalised(self):
        """'0-0' converges on the canonical 'O-O' spelling."""
        assert canonical_moves(["e4", "e5", "Nf3"]) == ["e4", "e5", "Nf3"]
        assert canonical_moves(["0-0"],
                               "r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1") == ["O-O"]


class TestReplay:
    def test_replay_reaches_the_expected_position(self):
        board = replay(["e4", "e5", "Nf3", "Nc6"])
        assert board.fen().startswith(
            "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R")

    def test_an_illegal_move_is_reported_with_its_index(self):
        with pytest.raises(ValueError) as excinfo:
            replay(["e4", "e5", "Qh9"])
        assert "3" in str(excinfo.value)

    def test_replay_honours_a_start_position(self):
        board = replay(["e8=Q"], "k7/4P3/8/8/8/8/8/4K3 w - - 0 1")
        assert "Q" in board.squares

    def test_load_pgn_returns_a_playable_final_position(self):
        text = export_pgn(OPENING, result="*")
        _tags, moves, _result, board = load_pgn(text)
        assert moves == OPENING
        assert board.legal_moves()

    def test_load_pgn_rejects_a_game_that_cannot_be_played(self):
        with pytest.raises(ValueError):
            load_pgn("1. e4 e5 2. Qh9 *")

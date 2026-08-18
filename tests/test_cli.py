"""Command handling, rendering and analysis reporting.

The interactive loop itself needs a terminal, but everything it delegates to
does not: commands are a pure function of (session, input), rendering is a pure
function of a board, and analysis is a pure function of a position. Testing
those directly covers the parts that can actually be wrong, without pretending
to drive a prompt.

Bad input gets as much attention as good input. A chess program is typed at by
humans, so "perft banana" and a malformed FEN must produce a message rather
than a traceback.
"""

import pytest

from termchess import Board
from termchess.analyze import analyse, format_score, render_analysis, run_perft
from termchess.cli import (
    LEVELS,
    Session,
    captured,
    format_history,
    game_over,
    handle_command,
    render,
    result_tag,
)
from termchess.constants import MATE
from termchess.search import Engine


@pytest.fixture
def session():
    return Session(Engine(depth=2, time_limit=1.0, blunder=0))


def run(session, text, capsys):
    """Run a command and return (action, printed output)."""
    action = handle_command(session, text)
    return action, capsys.readouterr().out


class TestRendering:
    def test_board_has_ranks_and_a_file_legend(self):
        text = render(Board())
        assert text.count("|") >= 16
        assert text.strip().endswith("a  b  c  d  e  f  g  h")

    def test_flipping_reverses_both_ranks_and_files(self):
        """Flipping is a 180-degree rotation, not a mirror.

        Both the rank order and the file legend reverse -- an earlier version
        of this test assumed only the ranks moved, and was wrong.
        """
        normal = render(Board()).splitlines()
        flipped = render(Board(), flipped=True).splitlines()
        assert len(normal) == len(flipped)
        assert normal[-1].split() == list("abcdefgh")
        assert flipped[-1].split() == list("hgfedcba")
        # Rank labels run 8..1 normally and 1..8 flipped.
        assert [line[1] for line in normal[1:9]] == list("87654321")
        assert [line[1] for line in flipped[1:9]] == list("12345678")

    def test_nothing_is_captured_at_the_start(self):
        gone = captured(Board())
        assert gone["white"] == [] and gone["black"] == []

    def test_captures_are_derived_from_the_position(self):
        """Derived, not tracked -- so it is right for any position at all."""
        gone = captured(Board.from_fen("4k3/8/8/8/8/8/8/4K3 w - - 0 1"))
        assert len(gone["white"]) == 15
        assert len(gone["black"]) == 15

    def test_capture_list_can_be_shown(self):
        text = render(Board.from_fen("4k3/8/8/8/8/8/8/3QK3 w - - 0 1"),
                      show_captures=True)
        assert "lost:" in text

    def test_history_formatting(self):
        assert format_history(["e4", "e5", "Nf3"]) == "1.e4 e5 2.Nf3"
        assert format_history([]) == "(no moves yet)"


class TestPositionCommands:
    def test_fen_prints_the_position(self, session, capsys):
        action, out = run(session, "fen", capsys)
        assert action == "continue"
        assert "rnbqkbnr" in out

    def test_moves_lists_twenty_at_the_start(self, session, capsys):
        _, out = run(session, "moves", capsys)
        assert "20 legal" in out

    def test_flip_toggles_orientation(self, session, capsys):
        before = session.flipped
        run(session, "flip", capsys)
        assert session.flipped is not before

    def test_board_redraws(self, session, capsys):
        _, out = run(session, "board", capsys)
        assert "a  b  c" in out

    def test_setfen_replaces_the_position(self, session, capsys):
        run(session, "setfen 4k3/8/8/8/8/8/8/4K3 w - - 0 1", capsys)
        assert session.board.fen().startswith("4k3")
        assert session.history == []

    def test_setfen_rejects_nonsense_without_crashing(self, session, capsys):
        _, out = run(session, "setfen not-a-fen", capsys)
        assert "valid FEN" in out or "Cannot" in out

    def test_setfen_without_an_argument_explains_itself(self, session, capsys):
        _, out = run(session, "setfen", capsys)
        assert "Usage" in out

    def test_history_command(self, session, capsys):
        _, out = run(session, "history", capsys)
        assert "no moves yet" in out


class TestAnalysisCommands:
    def test_eval_reports_a_static_score(self, session, capsys):
        _, out = run(session, "eval", capsys)
        assert "static evaluation" in out

    def test_analyze_reports_a_verdict_and_a_pv(self, session, capsys):
        _, out = run(session, "analyze", capsys)
        assert "verdict" in out and "pv" in out

    def test_analyze_accepts_a_fen_argument(self, session, capsys):
        _, out = run(session, "analyze 6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1",
                     capsys)
        assert "Ra8#" in out

    def test_analyze_rejects_a_bad_fen_without_crashing(self, session, capsys):
        _, out = run(session, "analyze total nonsense here now", capsys)
        assert "Cannot read" in out

    def test_hint_suggests_a_move(self, session, capsys):
        _, out = run(session, "hint", capsys)
        assert "Try" in out

    def test_perft_counts_nodes(self, session, capsys):
        _, out = run(session, "perft 2", capsys)
        assert "400" in out

    def test_perft_rejects_a_non_number(self, session, capsys):
        _, out = run(session, "perft banana", capsys)
        assert "Usage" in out

    def test_perft_rejects_an_absurd_depth(self, session, capsys):
        _, out = run(session, "perft 40", capsys)
        assert "between" in out


class TestSettingsCommands:
    def test_depth_can_be_set(self, session, capsys):
        run(session, "depth 5", capsys)
        assert session.engine.depth == 5

    def test_depth_rejects_out_of_range(self, session, capsys):
        run(session, "depth 999", capsys)
        assert session.engine.depth != 999

    def test_depth_without_argument_reports_the_current_value(self, session,
                                                              capsys):
        _, out = run(session, "depth", capsys)
        assert "Engine depth is" in out

    def test_time_can_be_set(self, session, capsys):
        run(session, "time 2.5", capsys)
        assert session.engine.time_limit == 2.5

    def test_time_rejects_out_of_range(self, session, capsys):
        run(session, "time 9999", capsys)
        assert session.engine.time_limit != 9999

    def test_time_without_argument_reports_the_current_value(self, session,
                                                             capsys):
        _, out = run(session, "time", capsys)
        assert "Engine time is" in out


class TestControlFlow:
    @pytest.mark.parametrize("word", ["quit", "exit", "q"])
    def test_quit_words(self, session, word):
        assert handle_command(session, word) == "quit"

    def test_new_restarts(self, session):
        assert handle_command(session, "new") == "new"

    def test_go_asks_the_engine_to_move(self, session):
        assert handle_command(session, "go") == "go"

    def test_help_prints_the_commands(self, session, capsys):
        _, out = run(session, "help", capsys)
        assert "analyze" in out and "perft" in out

    def test_a_move_is_not_a_command(self, session):
        """None is what tells the loop to try the input as a move."""
        assert handle_command(session, "e4") is None

    def test_undo_needs_two_plies(self, session, capsys):
        _, out = run(session, "undo", capsys)
        assert "Nothing to take back" in out


class TestSessionState:
    def test_push_and_pop_restore_everything(self, session):
        board = session.board
        before = board.fen()
        move = board.legal_moves()[0]
        session.push(move, "x")
        assert board.fen() != before
        session.pop()
        assert board.fen() == before
        assert session.history == []
        assert session.seen_hashes == [board.hash]

    def test_engine_move_advances_the_game(self, session):
        san, _score, _depth, _secs = session.engine_move()
        assert san
        assert session.history == [san]
        assert len(session.seen_hashes) == 2

    def test_undo_after_two_plies(self, session, capsys):
        session.engine_move()
        session.engine_move()
        run(session, "undo", capsys)
        assert session.history == []

    def test_pgn_export_round_trips_through_the_session(self, session):
        session.engine_move()
        text = session.to_pgn()
        assert "[Event" in text
        assert session.history[0] in text


class TestSaveAndLoad:
    def test_save_then_load_recovers_the_game(self, session, tmp_path, capsys):
        session.engine_move()
        expected = list(session.history)
        target = tmp_path / "game.pgn"

        _, out = run(session, "save %s" % target, capsys)
        assert "Wrote" in out
        assert target.exists()

        fresh = Session(Engine(depth=2, time_limit=1.0))
        _, out = run(fresh, "load %s" % target, capsys)
        assert "Loaded" in out
        assert fresh.history == expected

    def test_load_reports_a_missing_file(self, session, tmp_path, capsys):
        _, out = run(session, "load %s" % (tmp_path / "absent.pgn"), capsys)
        assert "Could not read" in out

    def test_load_reports_an_unplayable_game(self, session, tmp_path, capsys):
        bad = tmp_path / "bad.pgn"
        bad.write_text("1. e4 e5 2. Qh9 *")
        _, out = run(session, "load %s" % bad, capsys)
        assert "could not be replayed" in out

    def test_save_without_a_filename_explains_itself(self, session, capsys):
        _, out = run(session, "save", capsys)
        assert "Usage" in out

    def test_load_without_a_filename_explains_itself(self, session, capsys):
        _, out = run(session, "load", capsys)
        assert "Usage" in out


class TestGameEnd:
    def test_checkmate_is_reported(self):
        mated = Board.from_fen("R5k1/5ppp/8/8/8/8/8/6K1 b - - 0 1")
        assert "Checkmate" in (game_over(mated, {}) or "")

    def test_stalemate_is_reported(self):
        board = Board.from_fen("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")
        assert game_over(board, {}) == "Stalemate -- draw."

    def test_insufficient_material_is_reported(self):
        board = Board.from_fen("4k3/8/8/8/8/8/8/4K3 w - - 0 1")
        assert "insufficient" in game_over(board, {})

    def test_fifty_move_rule_is_reported(self):
        board = Board.from_fen("4k3/8/8/8/8/8/8/R3K3 w - - 100 60")
        assert "fifty-move" in game_over(board, {})

    def test_threefold_repetition_is_reported(self):
        board = Board()
        assert "threefold" in game_over(board, {board.key(): 3})

    def test_a_game_in_progress_has_no_verdict(self):
        assert game_over(Board(), {}) is None

    def test_result_tag_matches_the_verdict(self):
        mated = Board.from_fen("R5k1/5ppp/8/8/8/8/8/6K1 b - - 0 1")
        assert result_tag(mated, {}) == "1-0"
        assert result_tag(Board(), {}) == "*"

    def test_a_drawn_position_tags_as_a_draw(self):
        board = Board.from_fen("4k3/8/8/8/8/8/8/4K3 w - - 0 1")
        assert result_tag(board, {}) == "1/2-1/2"


class TestAnalysisReporting:
    def test_analyse_reports_every_documented_field(self):
        info = analyse(depth=3, time_limit=5.0)
        for key in ("fen", "static", "score", "best", "pv", "depth", "nodes",
                    "qnodes", "seconds", "nps", "tt_hits", "tt_probes"):
            assert key in info

    def test_mate_is_described_as_a_mate(self):
        assert "mate in 1" in format_score(MATE - 1, True)

    def test_score_is_shown_from_whites_point_of_view(self):
        """The search reports for the side to move; the reader expects White."""
        assert format_score(100, True) == "+1.00"
        assert format_score(100, False) == "-1.00"

    def test_render_analysis_is_readable(self):
        info = analyse(fen="6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1", depth=3,
                       time_limit=5.0)
        text = render_analysis(info, True)
        assert "best move" in text and "nodes" in text and "table" in text

    def test_run_perft_matches_the_known_count(self):
        nodes, elapsed = run_perft(None, 3)
        assert nodes == 8902
        assert elapsed >= 0


def test_every_difficulty_level_is_configured_sensibly():
    """Each level must search at least as deep and as long as the one below."""
    ordered = [LEVELS[key][1] for key in sorted(LEVELS)]
    assert [e.depth for e in ordered] == sorted(e.depth for e in ordered)
    assert [e.time_limit for e in ordered] == sorted(
        e.time_limit for e in ordered)
    # Only the weaker levels blunder on purpose.
    assert ordered[-1].blunder == 0
    assert ordered[0].blunder > 0

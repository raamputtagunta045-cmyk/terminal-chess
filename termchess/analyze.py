"""Position analysis -- the engine as a tool rather than an opponent.

Given a position, report what the engine thinks and how hard it worked to think
it: evaluation, best move, principal variation, and the search statistics that
say whether that verdict is worth trusting. A shallow search reporting a large
advantage and a deep one reporting the same thing are very different claims,
and only the statistics distinguish them.
"""

import time

from .board import Board
from .constants import MATE
from .evaluate import evaluate
from .perft import perft
from .search import Engine


def analyse(fen=None, depth=6, time_limit=10.0, board=None):
    """Search a position and return every statistic worth reporting."""
    if board is None:
        board = Board.from_fen(fen) if fen else Board()

    engine = Engine(depth=depth, time_limit=time_limit, blunder=0)
    started = time.perf_counter()
    move, score, reached = engine.choose(board)
    elapsed = time.perf_counter() - started

    return {
        "fen": board.fen(),
        "static": evaluate(board),
        "score": score,
        "best": engine.pv[0] if engine.pv else None,
        "pv": engine.pv,
        "depth": reached,
        "depth_cap": depth,
        "nodes": engine.nodes,
        "qnodes": engine.qnodes,
        "evals": engine.evals,
        "cutoffs": engine.cutoffs,
        "seconds": elapsed,
        "nps": engine.nodes / elapsed if elapsed else 0.0,
        "tt_entries": len(engine.tt),
        "tt_probes": engine.tt_probes,
        "tt_hits": engine.tt_hits,
        "tt_hit_rate": (engine.tt_hits / engine.tt_probes
                        if engine.tt_probes else 0.0),
        "null_cutoffs": engine.null_cutoffs,
        "researches": engine.researches,
        "repetitions": engine.repetitions,
        "legal_moves": len(board.legal_moves()),
        "move": move,
    }


def format_score(score, white_to_move):
    """Render a score from White's point of view, as convention expects.

    The search reports from the side to move's perspective, so a black-to-move
    position needs the sign flipped before a human reads it -- otherwise every
    other move of a game appears to swap who is winning.
    """
    if abs(score) > MATE - 100:
        plies = MATE - abs(score)
        moves = (plies + 1) // 2
        sign = 1 if score > 0 else -1
        if not white_to_move:
            sign = -sign
        return "mate in %d for %s" % (moves, "White" if sign > 0 else "Black")
    centipawns = score if white_to_move else -score
    return "%+.2f" % (centipawns / 100.0)


def render_analysis(info, white_to_move=True):
    """Human-readable analysis block."""
    nodes = info["nodes"]
    lines = [
        "  position   %s" % info["fen"],
        "  static     %+.2f  (evaluation before any search)"
        % (info["static"] / 100.0),
        "  verdict    %s" % format_score(info["score"], white_to_move),
        "  best move  %s" % (info["best"] or "-"),
        "  pv         %s" % (" ".join(info["pv"]) if info["pv"] else "-"),
        "",
        "  depth      %d of %d requested" % (info["depth"], info["depth_cap"]),
        "  nodes      %d  (%d in quiescence, %.0f%%)"
        % (nodes, info["qnodes"],
           100.0 * info["qnodes"] / nodes if nodes else 0),
        "  time       %.2fs at %.0f nodes/sec" % (info["seconds"], info["nps"]),
        "  cutoffs    %d" % info["cutoffs"],
        "  table      %d entries, %d of %d probes hit (%.1f%%)"
        % (info["tt_entries"], info["tt_hits"], info["tt_probes"],
           100.0 * info["tt_hit_rate"]),
    ]
    if info["null_cutoffs"] or info["researches"] or info["repetitions"]:
        lines.append("  pruning    %d null-move cutoffs, %d re-searches, "
                     "%d repetition draws"
                     % (info["null_cutoffs"], info["researches"],
                        info["repetitions"]))
    return "\n".join(lines)


def run_perft(fen, depth):
    """perft with timing, for the CLI command of the same name."""
    board = Board.from_fen(fen) if fen else Board()
    started = time.perf_counter()
    nodes = perft(board, depth)
    elapsed = time.perf_counter() - started
    return nodes, elapsed

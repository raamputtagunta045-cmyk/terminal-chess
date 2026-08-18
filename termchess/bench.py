#!/usr/bin/env python3
"""Deterministic fixed-depth benchmark for the search.

Run:
    python -m termchess.bench                     # human-readable table
    python -m termchess.bench --json out.json     # machine-readable
    python -m termchess.bench --compare out.json  # diff against a saved run
    python -m termchess.bench --quick             # shallower sanity check

    python chess_game.py --benchmark              # same thing, via the game

Why fixed depth rather than fixed time: a time-limited search visits a
different number of nodes on every machine and every run, so it cannot detect
a regression. At a fixed depth the node count is deterministic, which makes it
a real before/after signal -- wall-clock is reported too, but only node counts
are treated as authoritative.
"""

import argparse
import json
import platform
import sys
import time

from .board import Board
from .constants import MATE
from .notation import move_to_san
from .search import Engine

# name, FEN (None = starting position), depth
POSITIONS = [
    ("startpos", None, 5),
    ("italian",
     "r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/2N2N2/PPPP1PPP/R1BQK2R w KQkq - 4 5", 5),
    ("kiwipete",
     "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1", 4),
    ("promotion",
     "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1", 4),
    ("endgame", "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1", 6),
]

QUICK_DEPTH_PENALTY = 2


def _branching_factor(depth_stats):
    """Effective branching factor from the last two iterations.

    depth_stats holds *cumulative* node counts, so consecutive entries are
    differenced to recover the cost of each individual iteration.
    """
    if len(depth_stats) < 3:
        return None
    per_iter = [depth_stats[0][1]]
    for i in range(1, len(depth_stats)):
        per_iter.append(depth_stats[i][1] - depth_stats[i - 1][1])
    if per_iter[-2] <= 0:
        return None
    return per_iter[-1] / per_iter[-2]


def run_position(name, fen, depth):
    """Search one position to a fixed depth and collect every metric."""
    board = Board() if fen is None else Board.from_fen(fen)
    # A huge time limit means the depth is always reached, so the result is
    # reproducible; blunder=0 keeps the move choice deterministic.
    engine = Engine(depth=depth, time_limit=10 ** 6, blunder=0)

    started = time.perf_counter()
    move, score, reached = engine.choose(board)
    elapsed = time.perf_counter() - started

    probes = getattr(engine, "tt_probes", 0)
    hits = getattr(engine, "tt_hits", 0)
    pv = getattr(engine, "pv", None)

    return {
        "name": name,
        "fen": board.fen(),
        "depth": depth,
        "depth_reached": reached,
        "nodes": engine.nodes,
        "qnodes": engine.qnodes,
        "evals": engine.evals,
        "cutoffs": engine.cutoffs,
        "seconds": elapsed,
        "nps": engine.nodes / elapsed if elapsed else 0.0,
        "score": score,
        "best": move_to_san(board, move) if move else "-",
        "ebf": _branching_factor(engine.depth_stats),
        # Populated once the engine grows these features; reported as n/a
        # until then rather than silently omitted.
        "tt_probes": probes,
        "tt_hits": hits,
        "tt_hit_rate": (hits / probes) if probes else None,
        "pv": " ".join(pv) if pv else None,
    }


def _fmt_score(score):
    if abs(score) > MATE - 100:
        return "mate %d" % ((MATE - abs(score) + 1) // 2 * (1 if score > 0 else -1))
    return "%+.2f" % (score / 100.0)


def _fmt(value, spec, default="n/a"):
    return default if value is None else spec % value


def print_table(results):
    header = ("%-10s %5s %10s %10s %8s %9s %6s %8s %8s %s"
              % ("position", "depth", "nodes", "qnodes", "cutoffs",
                 "nps", "ebf", "time", "score", "best"))
    print(header)
    print("-" * len(header))
    for r in results:
        print("%-10s %5d %10d %10d %8d %9.0f %6s %7.2fs %8s %s"
              % (r["name"], r["depth_reached"], r["nodes"], r["qnodes"],
                 r["cutoffs"], r["nps"], _fmt(r["ebf"], "%.2f"),
                 r["seconds"], _fmt_score(r["score"]), r["best"]))
    print("-" * len(header))

    nodes = sum(r["nodes"] for r in results)
    qnodes = sum(r["qnodes"] for r in results)
    secs = sum(r["seconds"] for r in results)
    print("%-10s %5s %10d %10d %8d %9.0f %6s %7.2fs"
          % ("TOTAL", "", nodes, qnodes,
             sum(r["cutoffs"] for r in results),
             nodes / secs if secs else 0, "", secs))
    print("\nquiescence share: %.1f%% of all nodes" % (100.0 * qnodes / nodes))

    rates = [r["tt_hit_rate"] for r in results if r["tt_hit_rate"] is not None]
    if rates:
        print("transposition table hit rate: %.1f%%"
              % (100.0 * sum(rates) / len(rates)))
    else:
        print("transposition table: not implemented yet")


def compare(results, baseline_path):
    """Report node-count and speed deltas against a saved run."""
    with open(baseline_path) as handle:
        baseline = {r["name"]: r for r in json.load(handle)["results"]}

    header = "%-10s %12s %12s %9s %9s" % (
        "position", "nodes(base)", "nodes(now)", "nodes", "speed")
    print(header)
    print("-" * len(header))
    regressions = []
    for r in results:
        base = baseline.get(r["name"])
        if base is None:
            print("%-10s %12s %12d %9s %9s"
                  % (r["name"], "-", r["nodes"], "new", "new"))
            continue
        node_delta = 100.0 * (r["nodes"] - base["nodes"]) / base["nodes"]
        speed_delta = 100.0 * (r["nps"] - base["nps"]) / base["nps"]
        print("%-10s %12d %12d %+8.1f%% %+8.1f%%"
              % (r["name"], base["nodes"], r["nodes"], node_delta, speed_delta))
        if r["best"] != base["best"]:
            regressions.append("%s: best move changed %s -> %s"
                               % (r["name"], base["best"], r["best"]))
    print("-" * len(header))
    for note in regressions:
        print("NOTE  " + note)
    if not regressions:
        print("best move unchanged in every position")


def main(argv=None):
    # A literal rather than __doc__: docstrings are stripped under -OO.
    parser = argparse.ArgumentParser(
        description="Deterministic fixed-depth benchmark for the search.")
    parser.add_argument("--json", metavar="PATH",
                        help="write results as JSON for later comparison")
    parser.add_argument("--compare", metavar="PATH",
                        help="compare this run against a saved JSON run")
    parser.add_argument("--quick", action="store_true",
                        help="search %d plies shallower (fast sanity check)"
                             % QUICK_DEPTH_PENALTY)
    parser.add_argument("--only", metavar="NAME",
                        help="run a single position by name")
    args = parser.parse_args(argv)

    positions = POSITIONS
    if args.only:
        positions = [p for p in positions if p[0] == args.only]
        if not positions:
            parser.error("no position named %r (have: %s)"
                         % (args.only, ", ".join(p[0] for p in POSITIONS)))
    if args.quick:
        positions = [(n, f, max(1, d - QUICK_DEPTH_PENALTY))
                     for n, f, d in positions]

    print("python %s on %s\n" % (platform.python_version(), platform.system()))

    results = []
    for name, fen, depth in positions:
        sys.stdout.write("  searching %s to depth %d ... " % (name, depth))
        sys.stdout.flush()
        result = run_position(name, fen, depth)
        results.append(result)
        sys.stdout.write("%d nodes in %.2fs\n"
                         % (result["nodes"], result["seconds"]))
    print()
    print_table(results)

    if args.json:
        payload = {
            "python": platform.python_version(),
            "system": platform.system(),
            "results": results,
        }
        with open(args.json, "w") as handle:
            json.dump(payload, handle, indent=2)
        print("\nwrote %s" % args.json)

    if args.compare:
        print()
        compare(results, args.compare)

    return 0


if __name__ == "__main__":
    sys.exit(main())

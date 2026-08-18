"""Iterative-deepening negamax search with alpha-beta and quiescence.

The search mutates one shared board rather than copying it, so every make()
must be paired with an unmake() on *every* exit path -- including the TimeUp
exception that aborts a search mid-recursion. That pairing is enforced with
try/finally; without it a timed-out search leaves the board several plies deep
and the game appears to play moves nobody entered.

Move generation is called through the movegen free functions rather than the
Board methods: at hundreds of thousands of calls per search, skipping the bound
method costs nothing to read and saves a real fraction of the runtime.
"""

import random
import time

from . import movegen
from .constants import CHAR_VALUE, MATE
from .evaluate import VALUES, evaluate


class TimeUp(Exception):
    """Raised when the clock expires; unwinds to the last completed depth."""


class Engine:
    def __init__(self, depth=4, time_limit=3.0, blunder=0):
        self.depth = depth
        self.time_limit = time_limit
        self.blunder = blunder          # centipawn slack for weaker play
        self.nodes = 0
        self.deadline = 0.0
        # Instrumentation. These counters only observe the search, never steer
        # it, so they cannot change which move is chosen or how many nodes are
        # visited -- the benchmark relies on that.
        self.qnodes = 0                 # nodes spent inside quiescence
        self.evals = 0                  # static evaluations performed
        self.cutoffs = 0                # beta cutoffs taken
        self.depth_stats = []           # per-iteration (depth, nodes, secs, score)

    def _tick(self):
        # Checking the clock at every node would cost more than it saves, so
        # only every 2048th node consults it.
        self.nodes += 1
        if not self.nodes & 2047 and time.time() > self.deadline:
            raise TimeUp

    def _order(self, board, moves, best_first=None):
        """Sort moves most-promising first, so alpha-beta prunes sooner.

        MVV-LVA: prefer capturing the most valuable victim with the least
        valuable attacker. A cheap ordering heuristic is worth far more than a
        deeper search with none.
        """
        b = board.squares

        def score(mv):
            frm, to, promo = mv
            s = 0
            if mv == best_first:
                return 1_000_000
            victim = b[to]
            if victim != '.':
                # CHAR_VALUE is keyed by the raw piece character, so ordering
                # no longer pays for an .upper() call per capture considered.
                s += 10 * CHAR_VALUE[victim] - CHAR_VALUE[b[frm]]
            if promo:
                s += VALUES[promo]
            return s

        return sorted(moves, key=score, reverse=True)

    def quiesce(self, board, alpha, beta):
        """Search only captures, so evaluation never lands mid-trade.

        Stopping the main search at a fixed depth would happily evaluate a
        position with the queen hanging as if the recapture were not coming.
        """
        self._tick()
        self.qnodes += 1
        sign = 1 if board.white_to_move else -1
        self.evals += 1
        stand = sign * evaluate(board)
        if stand >= beta:
            self.cutoffs += 1
            return beta
        alpha = max(alpha, stand)

        captures = [m for m in movegen.pseudo_moves(board)
                    if board.squares[m[1]] != '.' or m[2]]
        for mv in self._order(board, captures):
            undo = board.make(mv)
            if movegen.attacked(board, board.king_sq(not board.white_to_move),
                                board.white_to_move):
                board.unmake(undo)
                continue
            try:
                score = -self.quiesce(board, -beta, -alpha)
            finally:
                # TimeUp unwinds through here; the move must come off the
                # board either way or the caller inherits a corrupt position.
                board.unmake(undo)
            if score >= beta:
                self.cutoffs += 1
                return beta
            alpha = max(alpha, score)
        return alpha

    def negamax(self, board, depth, alpha, beta, ply):
        self._tick()
        if board.halfmove >= 100 or not board.has_mating_material():
            return 0
        if depth <= 0:
            return self.quiesce(board, alpha, beta)

        moves = movegen.legal_moves(board)
        if not moves:
            # Mate is scored by distance from the root, so the search prefers
            # the quicker mate and delays being mated as long as possible.
            if board.in_check(board.white_to_move):
                return -MATE + ply
            return 0

        for mv in self._order(board, moves):
            undo = board.make(mv)
            try:
                score = -self.negamax(board, depth - 1, -beta, -alpha, ply + 1)
            finally:
                board.unmake(undo)
            if score >= beta:
                self.cutoffs += 1
                return beta
            alpha = max(alpha, score)
        return alpha

    def choose(self, board):
        """Iterative deepening; returns (move, score, depth_reached).

        Searching depth 1, then 2, then 3 rather than jumping straight to the
        target looks wasteful but is not: the shallow searches are cheap, and
        the best move they find is searched first at the next depth, which
        prunes far more than the extra iterations cost. It also guarantees a
        usable move is ready whenever the clock runs out.
        """
        self.nodes = 0
        self.qnodes = self.evals = self.cutoffs = 0
        self.depth_stats = []
        started = time.time()
        self.deadline = time.time() + self.time_limit
        root = movegen.legal_moves(board)
        if not root:
            return None, 0, 0

        best, best_score, reached = root[0], 0, 0
        scored = [(m, 0) for m in root]

        for depth in range(1, self.depth + 1):
            try:
                alpha, results = -MATE * 2, []
                for mv in self._order(board, root, best_first=best):
                    undo = board.make(mv)
                    try:
                        score = -self.negamax(board, depth - 1,
                                              -MATE * 2, -alpha, 1)
                    finally:
                        board.unmake(undo)
                    results.append((mv, score))
                    if score > alpha:
                        alpha = score
                results.sort(key=lambda x: x[1], reverse=True)
                scored = results
                best, best_score, reached = results[0][0], results[0][1], depth
                # Cumulative, not per-iteration: the benchmark differences
                # consecutive entries to estimate the branching factor.
                self.depth_stats.append(
                    (depth, self.nodes, time.time() - started, best_score))
                if abs(best_score) > MATE - 100:
                    break
            except TimeUp:
                # Keep the best move from the last *completed* iteration; a
                # partial one has searched only some of the root moves.
                break

        if self.blunder:
            # Weaker levels pick randomly among moves within a centipawn slack
            # of the best, so they blunder plausibly rather than at random.
            pool = [m for m, s in scored if s >= best_score - self.blunder]
            best = random.choice(pool)
            best_score = dict(scored)[best]
        return best, best_score, reached

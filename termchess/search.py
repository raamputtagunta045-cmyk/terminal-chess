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
from .evaluate import ENDGAME_MATERIAL, VALUES, evaluate


class TimeUp(Exception):
    """Raised when the clock expires; unwinds to the last completed depth."""


# Transposition table entry kinds.
EXACT = 0   # score is the true value of the position
LOWER = 1   # search failed high: the true value is at least this
UPPER = 2   # search failed low: the true value is at most this

# Scores beyond this magnitude encode a forced mate, and must be adjusted for
# ply before being stored or after being read back (see _to_tt / _from_tt).
MATE_BOUND = MATE - 1000

# Entries are small and the table is rebuilt per search, but a long search in a
# sharp position can still grow it without limit, so it is capped.
MAX_TT_ENTRIES = 1 << 20

# Delta pruning: how far short of alpha a capture may fall and still be
# searched. Generous enough to cover a follow-up tactic the static evaluation
# cannot see; tight enough to discard obviously hopeless captures.
DELTA_MARGIN = 200

# Delta pruning is switched off once material is this low. In a bare endgame a
# single pawn is often the whole game, so the assumption that a capture falling
# short of alpha is irrelevant stops holding. Shared with the evaluation rather
# than duplicated, so the threshold has one home.
DELTA_ENDGAME_FLOOR = ENDGAME_MATERIAL

# Ordering score bands. The exact numbers do not matter; the ordering between
# the bands does, and keeping them far apart makes that ordering obvious.
ORDER_TT_MOVE = 1_000_000
ORDER_CAPTURE = 100_000
ORDER_PROMOTION = 90_000
ORDER_KILLER = 80_000

MAX_PLY = 128

# Killer moves: quiet moves that caused a cutoff at this ply somewhere else in
# the tree. Two per ply is the usual compromise -- one is too forgetful, and
# more dilutes the signal.
KILLERS_PER_PLY = 2


class Engine:
    """Fail-soft alpha-beta.

    On a cutoff the search returns the score it actually found rather than the
    window bound it exceeded. Fail-hard (returning beta) is simpler, but the
    value it returns is a lie -- it says "at least beta" while claiming to be an
    exact number. Storing that in a transposition table poisons every later
    probe that reads it back as if it were meaningful, so the convention has to
    be fixed before a table exists, not after.
    """

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
        self.tt_probes = 0
        self.tt_hits = 0
        self.repetitions = 0            # nodes scored as a draw by repetition
        self.pv = []                    # principal variation, in SAN

        # Killer moves per ply, and a from/to table of how often a quiet move
        # has caused a cutoff anywhere. Both exist for the same reason: most
        # positions in a search are similar to their neighbours, so a move that
        # refuted one line usually refutes the next.
        self.killers = [[None] * KILLERS_PER_PLY for _ in range(MAX_PLY)]
        self.history = {}

        # hash -> (depth, flag, score, best_move)
        self.tt = {}
        # Position hashes along the line currently being searched, plus any
        # game history handed to choose(), for repetition detection.
        self.path = []

    @staticmethod
    def _to_tt(score, ply):
        """Convert a root-relative mate score to a node-relative one.

        A mate score means "mate in N plies counted from the root". The same
        position can be reached at different plies, so storing the root-relative
        number would make the table report mates at the wrong distance -- the
        engine would announce mate in 3 and then not deliver it. Storing the
        distance from *this node* makes the entry position-intrinsic.
        """
        if score > MATE_BOUND:
            return score + ply
        if score < -MATE_BOUND:
            return score - ply
        return score

    @staticmethod
    def _from_tt(score, ply):
        """Inverse of _to_tt: node-relative back to root-relative."""
        if score > MATE_BOUND:
            return score - ply
        if score < -MATE_BOUND:
            return score + ply
        return score

    def _tt_store(self, key, depth, flag, score, move, ply):
        # Depth-preferred replacement: a shallow result must not evict a deeper,
        # more expensive one, since the deep entry can serve shallow probes but
        # not the reverse.
        existing = self.tt.get(key)
        if existing is not None and existing[0] > depth:
            return
        if len(self.tt) >= MAX_TT_ENTRIES and existing is None:
            self.tt.clear()
        self.tt[key] = (depth, flag, self._to_tt(score, ply), move)

    def _tick(self):
        # Checking the clock at every node would cost more than it saves, so
        # only every 2048th node consults it.
        self.nodes += 1
        if not self.nodes & 2047 and time.time() > self.deadline:
            raise TimeUp

    def _order(self, board, moves, best_first=None, ply=None):
        """Sort moves most-promising first, so alpha-beta prunes sooner.

        Ordering matters more than almost anything else in an alpha-beta
        search: the sooner the best move is tried, the sooner everything after
        it can be cut off. The bands, in order:

          1. the transposition table's move -- a real result from a real search
          2. captures, by MVV-LVA (richest victim, cheapest attacker)
          3. promotions
          4. killers -- quiet moves that refuted a sibling line at this ply
          5. everything else, by how often it has caused a cutoff before

        Killers and history both exploit the same observation: positions near
        each other in the tree are nearly the same position, so a refutation
        that worked once usually works again.
        """
        b = board.squares
        killers = self.killers[ply] if ply is not None and ply < MAX_PLY else ()
        history = self.history

        def score(mv):
            if mv == best_first:
                return ORDER_TT_MOVE
            frm, to, promo = mv
            victim = b[to]
            if victim != '.':
                # CHAR_VALUE is keyed by the raw piece character, so ordering
                # no longer pays for an .upper() call per capture considered.
                return (ORDER_CAPTURE + 10 * CHAR_VALUE[victim]
                        - CHAR_VALUE[b[frm]])
            if promo:
                return ORDER_PROMOTION + VALUES[promo]
            if mv in killers:
                return ORDER_KILLER - killers.index(mv)
            return history.get(mv, 0)

        return sorted(moves, key=score, reverse=True)

    def _record_cutoff(self, mv, board, depth, ply):
        """Remember a quiet move that caused a cutoff.

        Captures are excluded: they are already ordered first by MVV-LVA, so
        recording them would only crowd out the quiet refutations that the
        ordering has no other way to find.

        History is weighted by depth squared because a cutoff found deep in the
        tree cost far more to establish and is correspondingly better evidence.
        """
        if board.squares[mv[1]] != '.' or mv[2]:
            return
        if ply < MAX_PLY:
            killers = self.killers[ply]
            if killers[0] != mv:
                killers[1] = killers[0]
                killers[0] = mv
        self.history[mv] = self.history.get(mv, 0) + depth * depth

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
            return stand
        best = stand
        if stand > alpha:
            alpha = stand

        captures = [m for m in movegen.pseudo_moves(board)
                    if board.squares[m[1]] != '.' or m[2]]
        # Delta pruning is unsound in a bare endgame, where a single pawn can
        # decide the game, so it is only applied while material remains.
        prune = board.heavy >= DELTA_ENDGAME_FLOOR
        squares = board.squares

        for mv in self._order(board, captures):
            if prune:
                # Best case for this capture: win the victim outright, plus the
                # upgrade if it is also a promotion. If even that cannot reach
                # alpha, searching it is wasted work.
                gain = CHAR_VALUE[squares[mv[1]]]
                if mv[2]:
                    gain += VALUES[mv[2]] - VALUES['P']
                if stand + gain + DELTA_MARGIN < alpha:
                    continue
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
            if score > best:
                best = score
                if score > alpha:
                    alpha = score
            if score >= beta:
                self.cutoffs += 1
                return best
        return best

    def negamax(self, board, depth, alpha, beta, ply):
        self._tick()
        # A position repeated along the current line is scored as a draw. One
        # repetition is enough: if a line returns to a position already on the
        # path, either side can keep returning to it, so the practical value is
        # a draw. Without this the engine cannot see a perpetual at all -- it
        # will happily walk into one while believing it is winning.
        if ply and board.hash in self.path:
            self.repetitions += 1
            return 0
        if board.halfmove >= 100 or not board.has_mating_material():
            # Checkmate on the hundredth half-move is a win, not a draw: the
            # game ends the instant the king cannot move, before any claim can
            # be made. Only worth the extra move generation on this rare path.
            if movegen.legal_moves(board):
                return 0
            return -MATE + ply if board.in_check(board.white_to_move) else 0
        if depth <= 0:
            return self.quiesce(board, alpha, beta)

        alpha_orig = alpha
        key = board.hash
        tt_move = None

        self.tt_probes += 1
        entry = self.tt.get(key)
        if entry is not None:
            e_depth, e_flag, e_score, e_move = entry
            # Even when the entry is too shallow to trust as a result, the move
            # it recorded is still the best guess available and is worth trying
            # first -- often a bigger win than the cutoff itself.
            tt_move = e_move
            if e_depth >= depth:
                score = self._from_tt(e_score, ply)
                if (e_flag == EXACT
                        or (e_flag == LOWER and score >= beta)
                        or (e_flag == UPPER and score <= alpha)):
                    self.tt_hits += 1
                    return score

        moves = movegen.legal_moves(board)
        if not moves:
            # Mate is scored by distance from the root, so the search prefers
            # the quicker mate and delays being mated as long as possible.
            if board.in_check(board.white_to_move):
                return -MATE + ply
            return 0

        best = -MATE * 2
        best_move = None
        self.path.append(key)
        try:
            for mv in self._order(board, moves, best_first=tt_move, ply=ply):
                undo = board.make(mv)
                try:
                    score = -self.negamax(board, depth - 1, -beta, -alpha,
                                          ply + 1)
                finally:
                    board.unmake(undo)
                if score > best:
                    best = score
                    best_move = mv
                    if score > alpha:
                        alpha = score
                if score >= beta:
                    self.cutoffs += 1
                    self._record_cutoff(mv, board, depth, ply)
                    self._tt_store(key, depth, LOWER, best, mv, ply)
                    return best

            # No move beat the original alpha, so `best` is only an upper bound
            # on the true value: everything here was searched with a window that
            # could not prove anything better.
            flag = UPPER if best <= alpha_orig else EXACT
            self._tt_store(key, depth, flag, best, best_move, ply)
            return best
        finally:
            # Pops on the cutoff return and on TimeUp alike; a leaked entry
            # would make an unrelated later line look like a repetition.
            self.path.pop()

    def choose(self, board, history=None):
        """Iterative deepening; returns (move, score, depth_reached).

        `history` is the hashes of positions already reached in the game. Pass
        it so the engine can see that repeating one of them is a draw -- without
        it the engine only sees repetitions that occur inside its own search.

        Searching depth 1, then 2, then 3 rather than jumping straight to the
        target looks wasteful but is not: the shallow searches are cheap, and
        the best move they find is searched first at the next depth, which
        prunes far more than the extra iterations cost. It also guarantees a
        usable move is ready whenever the clock runs out.
        """
        self.nodes = 0
        self.qnodes = self.evals = self.cutoffs = 0
        self.tt_probes = self.tt_hits = self.repetitions = 0
        self.killers = [[None] * KILLERS_PER_PLY for _ in range(MAX_PLY)]
        self.history = {}
        self.pv = []
        # Cleared per search so that the same position at the same depth always
        # produces the same answer, regardless of what was searched before it.
        self.tt = {}
        # The root position itself belongs on the path, so a line that returns
        # to it is recognised as a repetition.
        self.path = list(history) if history else []
        self.path.append(board.hash)
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

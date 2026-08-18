"""Terminal interface: board rendering and the interactive game loop."""

import sys
import time

from .analyze import analyse, format_score, render_analysis, run_perft
from .board import Board
from .constants import FILES, MATE, RANKS, START
from .notation import move_to_san, parse_move
from .pgn import export_pgn, load_pgn
from .search import Engine

GLYPHS = {'K': '♔', 'Q': '♕', 'R': '♖', 'B': '♗',
          'N': '♘', 'P': '♙', 'k': '♚', 'q': '♛',
          'r': '♜', 'b': '♝', 'n': '♞', 'p': '♟'}


def _unicode_ok():
    """Can this console actually print the chess glyphs?

    Asking forgiveness at print time would mean a crash halfway through a
    board; asking permission once at import lets the whole program fall back
    to plain letters cleanly.
    """
    try:
        '♔'.encode(sys.stdout.encoding or 'ascii')
        return True
    except (UnicodeEncodeError, LookupError, TypeError):
        return False


USE_GLYPHS = _unicode_ok()


def piece_glyph(p):
    return GLYPHS[p] if USE_GLYPHS else p


def captured(board):
    """Which pieces have left the board, per colour.

    Derived by comparing against the starting army rather than tracked as the
    game goes, so it stays correct through undo and through a game loaded from
    a FEN or a PGN file.
    """
    out = {}
    for side in ('white', 'black'):
        letters = 'PNBRQ' if side == 'white' else 'pnbrq'
        missing = []
        for letter in letters:
            gone = START.count(letter) - board.squares.count(letter)
            missing.extend([letter] * max(0, gone))
        out[side] = missing
    return out


def render(board, flipped=False, show_captures=False):
    rows = range(7, -1, -1) if flipped else range(8)
    files = range(7, -1, -1) if flipped else range(8)
    out = ["   +------------------------+"]
    for r in rows:
        cells = []
        for f in files:
            p = board.squares[r * 8 + f]
            if p == '.':
                cells.append('.' if (r + f) % 2 else ' ')
            else:
                cells.append(piece_glyph(p))
        out.append(" %s | %s |" % (RANKS[r], '  '.join(cells)))
    out.append("   +------------------------+")
    out.append("     " + '  '.join(FILES[f] for f in files))

    if show_captures:
        gone = captured(board)
        for side in ('white', 'black'):
            if gone[side]:
                out.append("   %s lost: %s"
                           % (side.capitalize(),
                              ' '.join(piece_glyph(p) for p in gone[side])))
    return '\n'.join(out)


def format_history(moves):
    """Move list in the conventional '1.e4 e5 2.Nf3' form."""
    if not moves:
        return "(no moves yet)"
    parts = []
    for index, san in enumerate(moves):
        if index % 2 == 0:
            parts.append("%d.%s" % (index // 2 + 1, san))
        else:
            parts.append(san)
    return ' '.join(parts)


HELP = """
Moves      e2e4, g1f3, e7e8q     (coordinates, optional promotion piece)
           e4, Nf3, exd5, O-O    (algebraic notation)

Position   board          redraw the position
           flip           flip the board orientation
           moves          list every legal move
           fen            print the FEN string
           setfen <FEN>   set up an arbitrary position
           history        the moves played so far
           new            restart the game

Analysis   eval           static evaluation, with no search at all
           analyze [FEN]  full search report: verdict, best move, PV, stats
           hint           the move the engine would play here
           go             let the engine move for you right now
           perft <n>      count leaf nodes at depth n (move-generation check)

Settings   depth <n>      set the engine's maximum search depth
           time <secs>    set the engine's time budget per move

Files      save <file>    write the game to a PGN file
           load <file>    read a game from a PGN file

           undo           take back your last move and the reply
           help           show this text
           quit           exit
"""

# Difficulty levels. `depth` is a ceiling, not a promise: iterative deepening
# stops at whichever of depth-or-clock arrives first, and in a sharp position
# the clock nearly always wins. The previous settings advertised depth 8 for
# Brutal when the engine never got past 6 in ten seconds, so Brutal and Hard
# played identically. These budgets were measured on the current engine --
# see BENCHMARKS.md -- and each level now genuinely searches deeper than the
# one below it.
LEVELS = {
    '1': ("Easy", Engine(depth=3, time_limit=0.5, blunder=90)),
    '2': ("Medium", Engine(depth=6, time_limit=2.0, blunder=25)),
    '3': ("Hard", Engine(depth=8, time_limit=6.0, blunder=0)),
    '4': ("Brutal", Engine(depth=12, time_limit=15.0, blunder=0)),
}


def ask(prompt, valid):
    while True:
        try:
            answer = input(prompt).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)
        if answer in valid:
            return answer
        print("  Please enter one of: %s" % ', '.join(valid))


def game_over(board, seen):
    """Return a result string, or None if the game continues."""
    if not board.legal_moves():
        if board.in_check(board.white_to_move):
            return "Checkmate -- %s wins." % ("Black" if board.white_to_move
                                              else "White")
        return "Stalemate -- draw."
    if board.halfmove >= 100:
        return "Draw by the fifty-move rule."
    if not board.has_mating_material():
        return "Draw -- insufficient material."
    if seen.get(board.key(), 0) >= 3:
        return "Draw by threefold repetition."
    return None


def result_tag(board, seen):
    """The PGN result token for the current position."""
    verdict = game_over(board, seen)
    if verdict is None:
        return "*"
    if verdict.startswith("Checkmate"):
        return "0-1" if board.white_to_move else "1-0"
    return "1/2-1/2"


class Session:
    """One game in progress, plus everything the commands act on."""

    def __init__(self, engine, human_white=True, board=None, start_fen=None):
        self.engine = engine
        self.human_white = human_white
        self.board = board if board is not None else Board()
        self.start_fen = start_fen or self.board.fen()
        self.flipped = not human_white
        self.seen = {self.board.key(): 1}
        # Real Zobrist keys: this is what the engine needs for repetition
        # detection. The SAN list below is for humans and for PGN.
        self.seen_hashes = [self.board.hash]
        self.undo_stack = []
        self.history = []

    def push(self, move, san):
        self.undo_stack.append(self.board.make(move))
        self.history.append(san)
        self.seen_hashes.append(self.board.hash)
        key = self.board.key()
        self.seen[key] = self.seen.get(key, 0) + 1

    def pop(self):
        self.seen[self.board.key()] -= 1
        self.board.unmake(self.undo_stack.pop())
        self.history.pop()
        self.seen_hashes.pop()

    def engine_move(self):
        """Let the engine choose; returns (san, score, depth, seconds)."""
        started = time.time()
        move, score, depth = self.engine.choose(
            self.board, history=self.seen_hashes)
        elapsed = time.time() - started
        if move is None:
            return None, 0, 0, elapsed
        san = move_to_san(self.board, move)
        self.push(move, san)
        return san, score, depth, elapsed

    def to_pgn(self):
        start = self.start_fen if self.start_fen != Board().fen() else None
        return export_pgn(self.history, start_fen=start,
                          result=result_tag(self.board, self.seen))


def _argument(raw):
    """Split 'analyze <rest>' into its argument, or ''."""
    parts = raw.split(None, 1)
    return parts[1].strip() if len(parts) > 1 else ''


def handle_command(session, raw):
    """Run one command.

    Returns 'continue', 'new', 'quit' or 'go'; None means the input was not a
    command at all and should be tried as a move instead.
    """
    words = raw.split()
    cmd = words[0].lower() if words else ''
    arg = _argument(raw)
    board = session.board

    if cmd in ('quit', 'exit', 'q'):
        return 'quit'
    if cmd in ('help', '?'):
        print(HELP)
        return 'continue'
    if cmd == 'new':
        return 'new'
    if cmd == 'go':
        return 'go'
    if cmd == 'board':
        print(render(board, session.flipped, show_captures=True))
        return 'continue'
    if cmd == 'flip':
        session.flipped = not session.flipped
        print(render(board, session.flipped, show_captures=True))
        return 'continue'
    if cmd == 'fen':
        print("  %s" % board.fen())
        return 'continue'
    if cmd == 'history':
        print("  %s" % format_history(session.history))
        return 'continue'
    if cmd == 'moves':
        legal = board.legal_moves()
        names = sorted(move_to_san(board, m, legal) for m in legal)
        print("  %d legal: %s" % (len(names), '  '.join(names)))
        return 'continue'

    if cmd == 'eval':
        from .evaluate import evaluate
        print("  static evaluation %+.2f from White's point of view"
              % (evaluate(board) / 100.0))
        return 'continue'

    if cmd == 'analyze':
        try:
            target = Board.from_fen(arg) if arg else board
        except (ValueError, IndexError) as exc:
            print("  Cannot read that position: %s" % exc)
            return 'continue'
        info = analyse(board=target, depth=session.engine.depth,
                       time_limit=session.engine.time_limit)
        print(render_analysis(info, target.white_to_move))
        return 'continue'

    if cmd == 'hint':
        info = analyse(board=board, depth=session.engine.depth,
                       time_limit=session.engine.time_limit)
        print("  Try %s  (%s)"
              % (info["best"] or "-",
                 format_score(info["score"], board.white_to_move)))
        return 'continue'

    if cmd == 'perft':
        try:
            depth = int(arg)
        except ValueError:
            print("  Usage: perft <depth>")
            return 'continue'
        if not 1 <= depth <= 6:
            print("  Depth must be between 1 and 6.")
            return 'continue'
        nodes, elapsed = run_perft(board.fen(), depth)
        print("  perft(%d) = %d in %.2fs (%.0f nodes/sec)"
              % (depth, nodes, elapsed, nodes / elapsed if elapsed else 0))
        return 'continue'

    if cmd == 'depth':
        try:
            value = int(arg)
        except ValueError:
            print("  Engine depth is %d. Usage: depth <n>"
                  % session.engine.depth)
            return 'continue'
        if not 1 <= value <= 20:
            print("  Depth must be between 1 and 20.")
            return 'continue'
        session.engine.depth = value
        print("  Engine depth set to %d (the clock may still stop it sooner)."
              % value)
        return 'continue'

    if cmd == 'time':
        # Named distinctly from the depth command's integer above: reusing one
        # `value` for both an int and a float made the two commands look
        # interchangeable when they are not.
        try:
            seconds = float(arg)
        except ValueError:
            print("  Engine time is %.1fs. Usage: time <seconds>"
                  % session.engine.time_limit)
            return 'continue'
        if not 0.05 <= seconds <= 300:
            print("  Time must be between 0.05 and 300 seconds.")
            return 'continue'
        session.engine.time_limit = seconds
        print("  Engine time budget set to %.1fs per move." % seconds)
        return 'continue'

    if cmd == 'setfen':
        if not arg:
            print("  Usage: setfen <FEN>")
            return 'continue'
        try:
            fresh = Board.from_fen(arg)
        except (ValueError, IndexError) as exc:
            print("  Not a valid FEN: %s" % exc)
            return 'continue'
        session.board = fresh
        session.start_fen = fresh.fen()
        session.seen = {fresh.key(): 1}
        session.seen_hashes = [fresh.hash]
        session.undo_stack = []
        session.history = []
        print(render(fresh, session.flipped, show_captures=True))
        return 'continue'

    if cmd == 'save':
        if not arg:
            print("  Usage: save <file.pgn>")
            return 'continue'
        try:
            with open(arg, 'w') as handle:
                handle.write(session.to_pgn())
        except OSError as exc:
            print("  Could not write %s: %s" % (arg, exc))
            return 'continue'
        print("  Wrote %d moves to %s" % (len(session.history), arg))
        return 'continue'

    if cmd == 'load':
        if not arg:
            print("  Usage: load <file.pgn>")
            return 'continue'
        try:
            with open(arg) as handle:
                text = handle.read()
            tags, moves, result, final = load_pgn(text)
        except OSError as exc:
            print("  Could not read %s: %s" % (arg, exc))
            return 'continue'
        except ValueError as exc:
            print("  That PGN could not be replayed: %s" % exc)
            return 'continue'
        session.board = final
        session.start_fen = tags.get("FEN") or Board().fen()
        session.history = list(moves)
        session.undo_stack = []
        session.seen = {final.key(): 1}
        session.seen_hashes = [final.hash]
        print("  Loaded %d moves (%s vs %s, %s)"
              % (len(moves), tags.get("White", "?"), tags.get("Black", "?"),
                 result))
        print("  Note: undo is unavailable for a game loaded from a file.")
        print(render(final, session.flipped, show_captures=True))
        return 'continue'

    if cmd == 'undo':
        if len(session.undo_stack) < 2:
            print("  Nothing to take back.")
            return 'continue'
        session.pop()
        session.pop()
        print(render(session.board, session.flipped, show_captures=True))
        return 'continue'

    return None


def report_engine_move(session, san, score, depth, elapsed):
    white_pov = score if not session.human_white else -score
    if abs(score) > MATE - 100:
        verdict = "mate in %d" % ((MATE - abs(score) + 1) // 2)
    else:
        verdict = "%+.2f" % (white_pov / 100.0)
    print("\r  Computer plays %-8s (depth %d, %s, %.1fs, %d nodes)"
          % (san, depth, verdict, elapsed, session.engine.nodes))
    if session.engine.pv:
        print("  expecting: %s" % ' '.join(session.engine.pv[:6]))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)

    if argv and argv[0] == '--analyze':
        fen = argv[1] if len(argv) > 1 else None
        target = Board.from_fen(fen) if fen else Board()
        info = analyse(board=target, depth=8, time_limit=10.0)
        print(render_analysis(info, target.white_to_move))
        return 0

    print("\n  T E R M I N A L   C H E S S\n")

    while True:
        colour = ask("  Play as (w)hite or (b)lack? ", {'w', 'b'})
        human_white = colour == 'w'

        print("\n  1) Easy    2) Medium    3) Hard    4) Brutal")
        level = ask("  Difficulty? ", set(LEVELS))
        label, engine = LEVELS[level]
        print("\n  %s, you are %s. Type 'help' for commands.\n"
              % (label, "White" if human_white else "Black"))

        session = Session(engine, human_white)
        print(render(session.board, session.flipped))

        restart = False
        while True:
            result = game_over(session.board, session.seen)
            if result:
                print("\n  %s\n" % result)
                break

            board = session.board
            if board.white_to_move == session.human_white:
                legal = board.legal_moves()
                try:
                    raw = input("  %d%s > " % (board.fullmove,
                                               '.' if board.white_to_move
                                               else '...')).strip()
                except (EOFError, KeyboardInterrupt):
                    print("\n  Goodbye.\n")
                    return 0
                if not raw:
                    continue

                action = handle_command(session, raw)
                if action == 'quit':
                    print("  Goodbye.\n")
                    return 0
                if action == 'new':
                    restart = True
                    break
                if action == 'continue':
                    continue
                if action == 'go':
                    print("  Thinking...", end='', flush=True)
                    san, score, depth, elapsed = session.engine_move()
                    if san:
                        report_engine_move(session, san, score, depth, elapsed)
                        print(render(session.board, session.flipped,
                                     show_captures=True))
                    continue

                move = parse_move(board, raw, legal)
                if move is None:
                    print("  Illegal or unrecognised move: %r "
                          "(try 'moves' for the list, 'help' for commands)"
                          % raw)
                    continue

                san = move_to_san(board, move, legal)
                session.push(move, san)
                print("  You play %s" % san)

            else:
                print("  Thinking...", end='', flush=True)
                san, score, depth, elapsed = session.engine_move()
                if san is None:
                    continue
                report_engine_move(session, san, score, depth, elapsed)
                print(render(session.board, session.flipped,
                             show_captures=True))
                if (session.board.in_check(session.board.white_to_move)
                        and session.board.legal_moves()):
                    print("  Check!")

        if restart:
            continue
        if session.history:
            print("  Moves: %s\n" % format_history(session.history))
        if ask("  Play again? (y/n) ", {'y', 'n'}) == 'n':
            print("  Thanks for playing.\n")
            return 0
        print()

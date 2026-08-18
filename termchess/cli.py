"""Terminal interface: board rendering and the interactive game loop."""

import sys
import time

from .board import Board
from .constants import FILES, MATE, RANKS
from .notation import move_to_san, parse_move
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


def render(board, flipped=False):
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
                cells.append(GLYPHS[p] if USE_GLYPHS else p)
        out.append(" %s | %s |" % (RANKS[r], '  '.join(cells)))
    out.append("   +------------------------+")
    out.append("     " + '  '.join(FILES[f] for f in files))
    return '\n'.join(out)


HELP = """
Moves      e2e4, g1f3, e7e8q     (coordinates, optional promotion piece)
           e4, Nf3, exd5, O-O    (algebraic notation)

Commands   board    redraw the position
           moves    list every legal move
           undo     take back your last move and the reply
           fen      print the FEN string
           flip     flip the board orientation
           new      restart the game
           help     show this text
           quit     exit
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


def main():
    print("\n  T E R M I N A L   C H E S S\n")

    while True:
        colour = ask("  Play as (w)hite or (b)lack? ", {'w', 'b'})
        human_white = colour == 'w'

        print("\n  1) Easy    2) Medium    3) Hard    4) Brutal")
        level = ask("  Difficulty? ", set(LEVELS))
        label, engine = LEVELS[level]
        print("\n  %s, you are %s. Type 'help' for commands.\n"
              % (label, "White" if human_white else "Black"))

        board = Board()
        flipped = not human_white
        seen = {board.key(): 1}
        undo_stack = []
        history = []
        # Zobrist keys of every position that has actually occurred. The engine
        # needs these to see that repeating one of them is a draw; without them
        # it can only detect repetitions inside its own search, and will
        # cheerfully repeat a position twice already on the board and hand away
        # a won game.
        seen_hashes = [board.hash]

        print(render(board, flipped))

        while True:
            result = game_over(board, seen)
            if result:
                print("\n  %s\n" % result)
                break

            if board.white_to_move == human_white:
                legal = board.legal_moves()
                try:
                    raw = input("  %d%s > " % (board.fullmove,
                                               '.' if board.white_to_move
                                               else '...')).strip()
                except (EOFError, KeyboardInterrupt):
                    print("\n  Goodbye.\n")
                    return

                cmd = raw.lower()
                if cmd in ('quit', 'exit', 'q'):
                    print("  Goodbye.\n")
                    return
                if cmd in ('help', '?'):
                    print(HELP)
                    continue
                if cmd == 'board':
                    print(render(board, flipped))
                    continue
                if cmd == 'flip':
                    flipped = not flipped
                    print(render(board, flipped))
                    continue
                if cmd == 'fen':
                    print("  %s" % board.fen())
                    continue
                if cmd == 'moves':
                    names = sorted(move_to_san(board, m, legal) for m in legal)
                    print("  %d legal: %s" % (len(names), '  '.join(names)))
                    continue
                if cmd == 'new':
                    break
                if cmd == 'undo':
                    if len(undo_stack) < 2:
                        print("  Nothing to take back.")
                        continue
                    for _ in range(2):
                        seen[board.key()] -= 1
                        board.unmake(undo_stack.pop())
                        history.pop()
                        seen_hashes.pop()
                    print(render(board, flipped))
                    continue

                mv = parse_move(board, raw, legal)
                if mv is None:
                    print("  Illegal or unrecognised move: %r "
                          "(try 'moves' for the list)" % raw)
                    continue

                san = move_to_san(board, mv, legal)
                undo_stack.append(board.make(mv))
                history.append(san)
                seen_hashes.append(board.hash)
                seen[board.key()] = seen.get(board.key(), 0) + 1
                print("  You play %s" % san)

            else:
                print("  Thinking...", end='', flush=True)
                started = time.time()
                mv, score, depth = engine.choose(board, history=seen_hashes)
                elapsed = time.time() - started
                if mv is None:
                    continue

                san = move_to_san(board, mv)
                undo_stack.append(board.make(mv))
                history.append(san)
                seen_hashes.append(board.hash)
                seen[board.key()] = seen.get(board.key(), 0) + 1

                # `score` is from the mover's (computer's) point of view;
                # report it from White's, as is conventional.
                white_pov = score if not human_white else -score
                if abs(score) > MATE - 100:
                    verdict = "mate in %d" % ((MATE - abs(score) + 1) // 2)
                else:
                    verdict = "%+.2f" % (white_pov / 100.0)
                print("\r  Computer plays %-8s (depth %d, %s, %.1fs, %d nodes)"
                      % (san, depth, verdict, elapsed, engine.nodes))
                print(render(board, flipped))

                if board.in_check(board.white_to_move) and board.legal_moves():
                    print("  Check!")

        if history:
            print("  Moves: %s\n" % ' '.join(
                ("%d.%s" % (i // 2 + 1, m) if i % 2 == 0 else m)
                for i, m in enumerate(history)))
        if ask("  Play again? (y/n) ", {'y', 'n'}) == 'n':
            print("  Thanks for playing.\n")
            return
        print()

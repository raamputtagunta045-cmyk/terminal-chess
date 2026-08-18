"""PGN import and export.

PGN is the interchange format for chess games, so supporting it is what lets a
game played here be opened in any other program -- and lets any game from
anywhere be replayed and analysed by this engine.

The movetext is deliberately parsed leniently and written strictly. Files in
the wild contain comments, variations, numeric annotation glyphs and move
numbers in inconsistent places; refusing them would make the feature useless.
What this module writes back is the plain, unambiguous subset.
"""

import re
import time

from .board import Board
from .notation import move_to_san, parse_move

# The Seven Tag Roster, in the order the standard requires.
SEVEN_TAG_ROSTER = ("Event", "Site", "Date", "Round", "White", "Black", "Result")

DEFAULT_TAGS = {
    "Event": "Casual game",
    "Site": "terminal-chess",
    "Round": "-",
    "White": "?",
    "Black": "?",
    "Result": "*",
}

RESULTS = ("1-0", "0-1", "1/2-1/2", "*")

_TAG = re.compile(r'\[\s*(\w+)\s*"([^"]*)"\s*\]')
_COMMENT_BRACE = re.compile(r"\{[^}]*\}")
_COMMENT_LINE = re.compile(r";[^\n]*")
_NAG = re.compile(r"\$\d+")
_MOVE_NUMBER = re.compile(r"\d+\s*\.(\.\.)?")


def today():
    """PGN dates are YYYY.MM.DD -- dots, not dashes."""
    return time.strftime("%Y.%m.%d")


def _strip_variations(text):
    """Remove parenthesised variations, which may nest."""
    out = []
    depth = 0
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif depth == 0:
            out.append(ch)
    return "".join(out)


def export_pgn(moves, tags=None, start_fen=None, result=None):
    """Render a game as PGN.

    `moves` is the list of SAN strings in order. `start_fen` is emitted only
    when the game did not begin from the standard position, which is what the
    SetUp/FEN tag pair means.
    """
    header = dict(DEFAULT_TAGS)
    header["Date"] = today()
    if tags:
        header.update(tags)
    if result is not None:
        header["Result"] = result
    if header["Result"] not in RESULTS:
        raise ValueError("bad result %r" % header["Result"])

    lines = []
    for key in SEVEN_TAG_ROSTER:
        lines.append('[%s "%s"]' % (key, header.get(key, "?")))
    if start_fen and start_fen != Board().fen():
        # SetUp="1" is what tells a reader the FEN tag is authoritative.
        lines.append('[SetUp "1"]')
        lines.append('[FEN "%s"]' % start_fen)
    for key in sorted(k for k in header
                      if k not in SEVEN_TAG_ROSTER and k not in ("SetUp", "FEN")):
        lines.append('[%s "%s"]' % (key, header[key]))

    # Numbering starts from the real position, not from move 1: a game resumed
    # from a FEN may begin on Black's turn halfway through.
    board = Board.from_fen(start_fen) if start_fen else Board()
    number = board.fullmove
    white_to_move = board.white_to_move

    tokens = []
    if not white_to_move and moves:
        tokens.append("%d..." % number)
    for san in moves:
        if white_to_move:
            tokens.append("%d." % number)
        tokens.append(san)
        if not white_to_move:
            number += 1
        white_to_move = not white_to_move
    tokens.append(header["Result"])

    body = []
    line = ""
    for token in tokens:
        if line and len(line) + len(token) + 1 > 79:
            body.append(line)
            line = token
        else:
            line = token if not line else line + " " + token
    if line:
        body.append(line)

    return "\n".join(lines) + "\n\n" + "\n".join(body) + "\n"


def parse_pgn(text):
    """Parse one PGN game into (tags, moves, result).

    `moves` are SAN strings exactly as they appeared; validating them against a
    board is replay()'s job, so a file can be inspected without being legal.
    """
    tags = dict(_TAG.findall(text))

    movetext = _TAG.sub("", text)
    movetext = _COMMENT_BRACE.sub(" ", movetext)
    movetext = _COMMENT_LINE.sub(" ", movetext)
    movetext = _strip_variations(movetext)
    movetext = _NAG.sub(" ", movetext)
    movetext = _MOVE_NUMBER.sub(" ", movetext)

    result = "*"
    moves = []
    for token in movetext.split():
        if token in RESULTS:
            result = token
            continue
        if set(token) <= {"."}:
            continue
        moves.append(token)

    if result == "*" and tags.get("Result") in RESULTS:
        result = tags["Result"]
    return tags, moves, result


def start_position(tags):
    """The FEN a game begins from, or None for the standard position."""
    fen = tags.get("FEN")
    return fen if fen else None


def replay(moves, start_fen=None):
    """Play SAN moves onto a board and return the final position.

    Raises ValueError naming the first illegal move. Stopping silently would
    leave the caller holding a position from the middle of a game it believed
    it had loaded in full.
    """
    board = Board.from_fen(start_fen) if start_fen else Board()
    for index, san in enumerate(moves):
        legal = board.legal_moves()
        move = parse_move(board, san, legal)
        if move is None:
            raise ValueError("illegal move %d (%r) in %s"
                             % (index + 1, san, board.fen()))
        board.make(move)
    return board


def canonical_moves(moves, start_fen=None):
    """Re-derive canonical SAN, normalising sloppy input.

    'Nf3', 'Nf3+', '0-0' and 'O-O' all parse. Re-emitting each move through
    move_to_san is what makes a round trip converge, instead of preserving
    whatever spelling the source file happened to use.
    """
    board = Board.from_fen(start_fen) if start_fen else Board()
    out = []
    for san in moves:
        legal = board.legal_moves()
        move = parse_move(board, san, legal)
        if move is None:
            raise ValueError("illegal move %r in %s" % (san, board.fen()))
        out.append(move_to_san(board, move, legal))
        board.make(move)
    return out


def load_pgn(text):
    """Parse and validate: returns (tags, canonical SAN moves, result, board)."""
    tags, moves, result = parse_pgn(text)
    start = start_position(tags)
    canonical = canonical_moves(moves, start)
    return tags, canonical, result, replay(canonical, start)

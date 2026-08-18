"""Frozen evaluation values -- a lock against accidental scoring changes.

These are the evaluation's current outputs, regenerated in the same commit as
any deliberate change to it, so the diff always shows the code change and the
score change together. A value that moves in isolation means something shifted
that nobody intended.

That distinction matters beyond tidiness: evaluation determines which tree the
search explores, so an unnoticed scoring change silently invalidates every
benchmark comparison drawn against an earlier run.
"""

import pytest

from termchess import Board, evaluate

# (FEN, expected centipawn score from White's point of view)
# The first eight are the shared corpus; the rest are sampled from a seeded
# 160-ply game, which reaches material imbalances and pawn structures that no
# hand-picked position would think to include.
FROZEN = [
    ('r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1', 0),
    ('rnbqkbnr/ppp1p1pp/8/3pPp2/8/8/PPPP1PPP/RNBQKBNR w KQkq f6 0 3', 23),
    ('8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1', -44),
    ('r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/2N2N2/PPPP1PPP/R1BQK2R w KQkq - 4 5', 0),
    ('r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1', 121),
    ('r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1', 89),
    ('8/8/8/4k3/8/8/4P3/4K3 w - - 0 40', 18),
    ('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1', 0),
    ('rnbqkbnr/pppppppp/8/8/6P1/8/PPPPPP1P/RNBQKBNR b KQkq g3 0 1', -18),
    ('rnbqkbnr/1pppp1pp/p4p2/6P1/8/5P2/PPPPP2P/RNBQKBNR b KQkq - 0 3', -13),
    ('rnbqk1nr/1pppb1pp/p3pp2/6P1/2P5/5P2/PPQPP2P/RNB1KBNR b KQkq - 2 5', -43),
    ('rnbqk1nr/1ppp2p1/p3ppp1/8/2P5/b1Q2P2/PP1PP2P/RNB1KBNR b KQkq - 1 7', -121),
    ('rnbq2nr/1pppk1p1/p3pp2/6p1/2P1P3/b1Q2P2/PP1PK2P/RNB2BNR b - - 1 9', -102),
    ('1nbq2nr/rpp1k1p1/pQ1ppp2/6p1/2P1P3/b4P2/PP1PK2P/RNB2BNR b - - 3 11', -122),
    ('1nb2qnr/rp2k1p1/pp1ppp2/6p1/1PP1P3/b4P2/P2P3P/RNB1KBNR b - - 2 13', -998),
    ('1nb3nr/rp2kqp1/pp2pp2/3p2p1/1PPPP2P/b4P2/P7/RNB1KBNR b - h3 0 15', -984),
    ('1nb2qnr/rp2k1p1/pp2pp2/3p2p1/1bPPP2P/5P2/P2B4/RN1K1BNR b - - 3 17', -1086),
    ('1nb3nr/rp2k1p1/pp2pp2/3p2pq/1bPPP2P/2B2P1R/P7/RN1K1BN1 b - - 7 19', -1086),
    ('2b2knr/rp1n2p1/pp2pp2/3p2pq/1bPPP2P/2B2P2/P7/RNK2BNR b - - 11 21', -1131),
    ('2b2knr/rp1n2p1/pp2pp2/3p2pq/1bPPP2P/2B2P2/P5B1/RN1K2NR b - - 15 23', -1114),
    ('2b1qknr/rp1n2p1/pp3p2/3pp1p1/PbPPP2P/2B2P1N/6B1/RN1K3R b - - 1 25', -1124),
    ('2b1qknr/rp1n2p1/p4p2/3pp1p1/pbPPP2P/2N2P1N/1B4B1/R2K3R b - - 1 27', -1170),
    ('2b1qknr/rp1n2p1/p2b1p2/4p1p1/pBPPp2P/2N2P1N/6B1/R2K3R b - - 1 29', -1293),
    ('2b1qkn1/rp1n2pr/p2b1p2/4p1p1/pBPP1P1P/2N1p2N/6B1/R2K1R2 b - - 2 31', -1287),
    ('r1b1qkn1/1p1n2pr/p2b1p2/4p3/pBPPBPpP/4p2N/8/RN1K1R2 b - - 1 33', -1332),
    ('r1b2kn1/1p1n1qpr/3b1p2/p3p3/p1PPBPpP/4p2N/4K3/RN2BR2 b - - 1 35', -1339),
    ('r1b2kn1/1p1n2pr/4qp2/p3p3/pbPPBPpP/N1B1p2N/4K3/R4R2 b - - 5 37', -1309),
    ('r1b2kn1/1p1n3r/4qp2/p3pBp1/p1PP1PpP/R1B1p2N/4K3/5R2 b - - 0 39', -1238),
    ('r1b2kn1/1p1n3r/5p2/p3p1p1/p1qP1PpP/R1BBp2N/4K3/4R3 b - - 1 41', -1332),
    ('r1b2k2/1p1nn3/5p1r/p3p1p1/pBqP1PpP/R2Bp2N/8/4RK2 b - - 5 43', -1396),
    ('r1b5/3nnk2/1p3p1r/p3p1p1/pBqP1PpP/2R1p2N/4B3/4RK2 b - - 1 45', -1384),
    ('r1bBk3/3n4/1p3p1r/p3p1p1/pq1P1PpP/2R1p2N/4B3/4RK2 b - - 2 47', -1051),
    ('2bBk3/3n4/rp3p1r/p3p1p1/p2q1PpP/2R1p2N/4B3/R3K3 b - - 1 49', -1182),
    ('2bBk3/3n4/rp3p2/p3p1pr/p4qpP/R2Bp2N/8/R3K3 b - - 1 51', -1298),
    ('2bBk3/8/rp3p2/p1n1p1pr/p5pP/R2Bp2N/2K5/R4q2 b - - 5 53', -1284),
    ('2bBk3/8/rp3p2/p3p1pr/R3n1pP/3Bpq1N/2K5/5R2 b - - 2 55', -1219),
    ('3Bk3/1b6/rp3p2/p3p1pr/R3n2P/3Bpq1p/8/RK6 b - - 1 57', -1591),
    ('3Bk3/8/rp3pB1/p3p1pr/R1b4P/4pq1p/8/RK6 b - - 2 59', -1268),
    ('3B4/3k4/rp2bp2/p3pBpr/R6P/4pq1p/2K5/R7 b - - 6 61', -1279),
    ('2k5/8/rB2bp2/p4Bpr/R3p2P/4pq1p/2K5/4R3 b - - 0 63', -1151),
    ('2k5/8/1r2bpB1/p5Pr/R3pq2/4p2p/2K5/4R3 b - - 0 65', -1416),
    ('2k5/8/4bPBr/p7/1r2pq2/4p2p/2K5/R3R3 b - - 2 67', -1242),
    ('1rk5/7B/4bP1r/8/p3pq2/4p2p/2K5/R3R3 b - - 1 69', -1275),
    ('1rk5/5b1B/5P1r/8/p3p3/4Rq1p/2K5/2R5 b - - 2 71', -1160),
    ('2k5/5b2/5P1r/8/p3B3/1r3q1p/2K5/2R5 b - - 0 73', -1510),
    ('1k6/5b2/5P1r/8/p3B3/1r5p/3K4/5R1q b - - 4 75', -1526),
    ('1k5r/5b2/5P2/6R1/p3q3/1r5p/3K4/8 b - - 1 77', -1870),
    ('1k6/5b2/5P2/6R1/p3qr2/1r5p/3K4/8 b - - 5 79', -1882),
]


@pytest.mark.parametrize("fen,expected", FROZEN,
                         ids=[str(i) for i in range(len(FROZEN))])
def test_evaluation_is_unchanged(fen, expected):
    assert evaluate(Board.from_fen(fen)) == expected, (
        "evaluation changed for %s" % fen)


def test_corpus_is_not_trivially_balanced():
    """Guard the guard: frozen zeroes would prove nothing."""
    scores = [score for _, score in FROZEN]
    assert len([s for s in scores if s != 0]) > 40
    assert max(scores) - min(scores) > 1000

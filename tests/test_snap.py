import unittest
from models import Sentence, Clip
from snap import snap_clips

SENTS = [Sentence("A.", 688.0, 690.0), Sentence("B.", 690.7, 720.0),
         Sentence("C.", 720.5, 747.0), Sentence("D.", 747.5, 760.0)]
WARN = " ⚠ پایان وسط جمله"


class SnapTests(unittest.TestCase):
    def test_snaps_to_nearest_sentence_start_and_end(self):
        out = snap_clips([Clip(1, 691.5, 746.0, "r")], SENTS)
        self.assertEqual((out[0].start, out[0].end), (690.7, 747.0))
        self.assertEqual(out[0].reason, "r")

    def test_no_sentence_end_within_tolerance_keeps_end_and_warns(self):
        sents = [Sentence("B.", 690.7, 700.0), Sentence("C.", 700.5, 800.0)]
        out = snap_clips([Clip(1, 691.0, 750.0, "r")], sents)
        self.assertEqual(out[0].end, 750.0)
        self.assertEqual(out[0].reason, "r" + WARN)

    def test_result_sorted_by_rank(self):
        out = snap_clips([Clip(2, 691.5, 746.0, "x"), Clip(1, 721.0, 759.0, "y")], SENTS)
        self.assertEqual([c.rank for c in out], [1, 2])

    def test_end_is_always_after_start(self):
        sents = [Sentence("S.", 100.0, 103.0), Sentence("T.", 103.5, 104.0)]
        out = snap_clips([Clip(1, 102.9, 103.1, "r")], sents)
        self.assertLess(out[0].start, out[0].end)
        self.assertEqual((out[0].start, out[0].end), (103.5, 104.0))


if __name__ == "__main__":
    unittest.main()

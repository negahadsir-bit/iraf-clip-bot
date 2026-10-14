404: Not Found





from silence import detect_silences, drop_overlaps, snap_to_silence






























class LimitTests(unittest.TestCase):
    def test_snapping_never_pushes_a_clip_past_75_seconds(self):
        out = snap_to_silence([Clip(1, 14.0, 85.0, "r")], [(9.0, 11.0), (88.0, 89.0)])
        self.assertLessEqual(out[0].end - out[0].start, 75.0)

    def test_already_long_clip_is_not_fought_over(self):
        out = snap_to_silence([Clip(1, 10.0, 90.0, "r")], [])
        self.assertEqual((out[0].start, out[0].end), (10.0, 90.0))


class OverlapTests(unittest.TestCase):
    def test_clip_inside_another_is_dropped(self):
        a, b = Clip(5, 423.6, 485.4, "a"), Clip(10, 438.6, 478.7, "b")
        out = drop_overlaps([a, b])
        self.assertEqual([c.reason for c in out], ["a"])

    def test_top_clip_wins_over_better_ranked_regular_one(self):
        a, b = Clip(1, 10.0, 70.0, "a"), Clip(2, 50.0, 110.0, "b", top=True)
        self.assertEqual([c.reason for c in drop_overlaps([a, b])], ["b"])

    def test_touching_clips_are_kept_and_ranks_renumbered(self):
        a, b, c = Clip(1, 0.0, 40.0, "a"), Clip(2, 10.0, 30.0, "b"), Clip(3, 40.5, 90.0, "c")
        out = drop_overlaps([a, b, c])
        self.assertEqual([(x.rank, x.reason) for x in out], [(1, "a"), (2, "c")])


import subprocess
import tempfile
import unittest
from pathlib import Path

from models import Clip
from silence import detect_silences, drop_overlaps, snap_to_silence


class SnapTests(unittest.TestCase):
    SIL = [(10.0, 12.0), (30.0, 31.0), (70.0, 72.0)]

    def test_start_moves_to_nearest_speech_onset_within_window(self):
        out = snap_to_silence([Clip(1, 13.5, 68.0, "r")], self.SIL)
        self.assertEqual(out[0].start, 12.0)

    def test_end_moves_to_nearest_pause_start_within_window(self):
        out = snap_to_silence([Clip(1, 13.5, 68.5, "r")], self.SIL)
        self.assertEqual(out[0].end, 70.0)

    def test_far_boundaries_are_left_alone(self):
        out = snap_to_silence([Clip(1, 20.0, 50.0, "r")], self.SIL)
        self.assertEqual((out[0].start, out[0].end), (20.0, 50.0))

    def test_snapping_never_makes_clip_shorter_than_20_seconds(self):
        out = snap_to_silence([Clip(1, 8.0, 29.0, "r")], self.SIL)
        self.assertGreaterEqual(out[0].end - out[0].start, 20.0)

    def test_rank_and_reason_are_kept(self):
        out = snap_to_silence([Clip(7, 13.5, 68.5, "why")], self.SIL)
        self.assertEqual((out[0].rank, out[0].reason), (7, "why"))

    def test_no_silences_returns_clips_unchanged(self):
        c = Clip(1, 5.0, 60.0, "r")
        self.assertEqual(snap_to_silence([c], []), [c])


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


class DetectTests(unittest.TestCase):
    def test_finds_the_pause_in_real_audio(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.wav"
            subprocess.run(
                ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                 "aevalsrc=if(between(t\\,2\\,3)\\,0\\,0.5*sin(2*PI*440*t)):d=5:s=16000",
                 str(p)], check=True)
            sil = detect_silences(p)
        self.assertEqual(len(sil), 1)
        self.assertAlmostEqual(sil[0][0], 2.0, delta=0.15)
        self.assertAlmostEqual(sil[0][1], 3.0, delta=0.15)


if __name__ == "__main__":
    unittest.main()

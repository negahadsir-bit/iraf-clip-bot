import unittest
from models import Word, Sentence
from timeline import fix_word_times, words_to_sentences, to_transcript


def W(text, s, e=None):
    return Word(text, s, s + 0.4 if e is None else e)


class TimelineTests(unittest.TestCase):
    def test_broken_huge_start_is_pulled_between_neighbours(self):
        words = [W("a", 12.9), W("b", 13.4), W("c", 1003.2), W("d", 14.0)]
        fixed = fix_word_times(words)
        starts = [w.start for w in fixed]
        self.assertEqual(starts, sorted(starts))
        self.assertTrue(13.4 <= starts[2] <= 14.0)

    def test_jump_over_20s_is_interpolated(self):
        words = [W("a", 10.0), W("b", 11.0), W("c", 40.0), W("d", 12.0)]
        fixed = fix_word_times(words)
        self.assertAlmostEqual(fixed[2].start, 11.5, places=2)

    def test_sentences_split_on_terminators_and_use_word_times(self):
        words = [W("سلام", 1.0, 1.4), W("دنیا.", 1.5, 2.0),
                 W("چطوری؟", 2.5, 3.0), W("خوبم", 3.2, 3.6)]
        sents = words_to_sentences(words)
        self.assertEqual([s.text for s in sents], ["سلام دنیا.", "چطوری؟", "خوبم"])
        self.assertEqual((sents[0].start, sents[0].end), (1.0, 2.0))
        self.assertEqual((sents[1].start, sents[1].end), (2.5, 3.0))

    def test_unreliable_word_end_uses_next_start_or_700ms(self):
        words = [W("الف", 1.0, 900.0), W("ب.", 2.0, 2.3)]
        s = words_to_sentences(words)[0]
        self.assertEqual(s.end, 2.3)
        lone = words_to_sentences([W("پایان.", 5.0, 900.0)])[0]
        self.assertAlmostEqual(lone.end, 5.7, places=3)

    def test_transcript_line_is_minute_second_floor(self):
        out = to_transcript([Sentence("متن", 67.9, 70.0), Sentence("دوم", 600.0, 605.0)])
        self.assertEqual(out.splitlines(), ["1:07 متن", "10:00 دوم"])


if __name__ == "__main__":
    unittest.main()

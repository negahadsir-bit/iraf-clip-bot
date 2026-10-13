import re
import unittest
from models import Sentence, Clip
from formatting import fmt_time, format_messages


class FormattingTests(unittest.TestCase):
    def test_fmt_time_one_decimal(self):
        self.assertEqual(fmt_time(1091.2), "18:11.2")
        self.assertEqual(fmt_time(59.96), "1:00.0")
        self.assertEqual(fmt_time(5.0), "0:05.0")

    def test_single_clip_matches_spec_layout(self):
        sents = [Sentence("الف ب ج.", 10.0, 20.0), Sentence("د ه و.", 20.5, 50.0)]
        msgs = format_messages([Clip(1, 10.0, 50.0, "دلیل")], sents, 1565.0)
        self.assertEqual(len(msgs), 1)
        self.assertEqual(
            msgs[0],
            "✅ 1 پیشنهاد برش (مدت قسمت 26:05)\n\n"
            "1) 0:10.0 – 0:50.0 (40ث)\n"
            "   شروع: «الف ب ج. د ه و.»\n"
            "   پایان: «الف ب ج. د ه و.»\n"
            "   چرا: دلیل")

    def test_long_text_shows_first_and_last_seven_words(self):
        words = [f"w{i}" for i in range(20)]
        sents = [Sentence(" ".join(words) + ".", 0.0, 40.0)]
        msg = format_messages([Clip(1, 0.0, 40.0, "r")], sents, 100.0)[0]
        self.assertIn("شروع: «w0 w1 w2 w3 w4 w5 w6…»", msg)
        self.assertIn("پایان: «…w13 w14 w15 w16 w17 w18 w19.»", msg)

    def test_many_long_suggestions_split_without_cutting_a_suggestion(self):
        sents = [Sentence("کلمه " * 10 + ".", float(i * 100), float(i * 100 + 60)) for i in range(40)]
        clips = [Clip(i + 1, float(i * 100), float(i * 100 + 60), "دلیل " * 40) for i in range(40)]
        msgs = format_messages(clips, sents, 5000.0)
        self.assertGreater(len(msgs), 1)
        self.assertTrue(all(len(m) <= 4096 for m in msgs))
        headers = re.findall(r"^(\d+)\) ", "\n".join(msgs), re.M)
        self.assertEqual(sorted(headers, key=int), [str(i) for i in range(1, 41)])

    def test_absurdly_long_reason_still_fits_one_message(self):
        sents = [Sentence("متن.", 0.0, 40.0)]
        msgs = format_messages([Clip(1, 0.0, 40.0, "x" * 5000)], sents, 100.0)
        self.assertTrue(all(len(m) <= 4096 for m in msgs))


if __name__ == "__main__":
    unittest.main()

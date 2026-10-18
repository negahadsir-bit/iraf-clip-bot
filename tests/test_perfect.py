import unittest
from pathlib import Path
from types import SimpleNamespace as NS

import studio
from hearing import HybridClient

DRAFT = ("الحمدلله می‌گم یعنی ببینید ما خب داشتیم مشتری که آمده در خانه کابل آمده غذای خودا خورد "
         "آمد وقت حساب کردن گفت من با یک گارد آمده بودم اینجا گفتم چطور گفت من کاملاً گارد داشتم ما")
GOOD = ("می‌گم یعنی ببینید ما خب داشتیم مشتری که آمده در خانه کابل آمده غذای خود را خورد "
        "آمد وقت حساب کردن گفت من با یک گارد آمده بودم اینجا گفتم چطور گفت من کاملاً گارد داشتم.")


class Client:
    """correct_text echoes the draft; caption_text answers from a script."""

    def __init__(self, answers, boom=False):
        self.answers, self.boom, self.calls = list(answers), boom, []

    def correct_text(self, audio, draft):
        return draft

    def caption_text(self, audio, candidates):
        self.calls.append(list(candidates))
        if self.boom:
            raise RuntimeError("down")
        return self.answers.pop(0) if self.answers else ""


class PerfectTextTests(unittest.TestCase):
    def run_it(self, client, text=DRAFT):
        return studio.perfect_text(client, Path("a.mp3"), text)

    def test_dari_made_standard_and_stray_edge_words_cut(self):
        out = self.run_it(Client([GOOD, GOOD]))
        self.assertTrue(out.startswith("می‌گم"))
        self.assertIn("خود را خورد", out)
        self.assertTrue(out.endswith("داشتم."), out)

    def test_two_listenings_second_one_only_verifies(self):
        c = Client([GOOD, GOOD])
        self.run_it(c)
        self.assertEqual(len(c.calls), studio.CAPTION_ROUNDS)
        self.assertEqual(c.calls[1], [GOOD])

    def test_rewrite_of_the_speech_is_rejected(self):
        out = self.run_it(Client(["این متن کاملاً چیز دیگری است که ربطی به گفتار ندارد و بلند هم هست"]))
        self.assertIn("غذای خودا خورد", out)

    def test_cutting_half_the_text_is_rejected(self):
        half = " ".join(DRAFT.split()[:15])
        out = self.run_it(Client([half]))
        self.assertEqual(out.split()[-1], "ما")

    def test_verifying_round_cannot_drift(self):
        drift = (GOOD.replace("گارد", "کارت").replace("کابل", "هرات").replace("مشتری", "میزبان")
                 .replace("حساب", "پول").replace("چطور", "چرا"))
        out = self.run_it(Client([GOOD, drift]))
        self.assertEqual(out, GOOD)

    def test_failing_listening_keeps_the_spelling_pass_result(self):
        out = self.run_it(Client([], boom=True), text="مي خواهم بروم")
        self.assertEqual(out, "می‌خواهم بروم")

    def test_client_without_caption_support_still_works(self):
        class Old:
            def correct_text(self, audio, draft):
                return draft
        self.assertEqual(self.run_it(Old(), text="مي خواهم"), "می‌خواهم")

    def test_empty_answer_is_ignored(self):
        self.assertIn("خودا", self.run_it(Client([""])))


class HybridCaptionTests(unittest.TestCase):
    def test_second_engine_text_is_added_to_the_readings(self):
        seen = []
        g = NS(caption_text=lambda audio, cands: seen.append(list(cands)) or "x")
        d = NS(listen=lambda audio: {"text": "متن دیپ‌گرام", "words": [{"text": "a", "heard": "a", "start": 0, "end": 1}]})
        import tempfile
        p = Path(tempfile.mkdtemp()) / "a.mp3"
        p.write_bytes(b"1")
        HybridClient(g, d).caption_text(p, ["پیش‌نویس"])
        self.assertEqual(seen[0], ["پیش‌نویس", "متن دیپ‌گرام"])


class GeminiCaptionTests(unittest.TestCase):
    def test_prompt_lists_readings_and_the_rules(self):
        from transcribe import GeminiClient
        seen = []

        def generate(model, contents, config):
            seen.append(contents[0])
            return NS(text='[{"text": "نهایی"}]')
        api = NS(files=NS(upload=lambda file: "F"), models=NS(list=lambda: [], generate_content=generate))
        c = GeminiClient.__new__(GeminiClient)
        c._client, c._models, c._careful_models = api, ["flash"], None
        self.assertEqual(c.caption_text(Path("a.mp3"), ["اول", "دوم"]), "نهایی")
        p = seen[0]
        for needle in ("خوانش 1: «اول»", "خوانش 2: «دوم»", "هستند", "خود را", "بی‌معنی"):
            self.assertIn(needle, p)


if __name__ == "__main__":
    unittest.main()

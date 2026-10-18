import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from types import SimpleNamespace as NS

import deepgram
from hearing import HybridClient, words_match
from transcribe import _hint

BODY = {"results": {"channels": [{"alternatives": [{
    "transcript": "من به خانه رفتم",
    "words": [{"word": "من", "start": 0.1, "end": 0.3}, {"word": "به", "start": 0.3, "end": 0.45},
              {"word": "خانه", "start": 0.5, "end": 0.9}, {"word": "رفتم", "start": 1.0, "end": 1.4}]}]}]}}


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def opener_returning(body):
    calls = []

    def f(req, timeout):
        calls.append(req)
        return Resp(json.dumps(body).encode())
    f.calls = calls
    return f


def opener_failing(code=None, times=99):
    calls = []

    def f(req, timeout):
        calls.append(req)
        if len(calls) > times:
            return Resp(json.dumps(BODY).encode())
        if code:
            raise urllib.error.HTTPError("u", code, "x", {}, io.BytesIO(b"{}"))
        raise ConnectionError("down")
    f.calls = calls
    return f


def mp3():
    d = tempfile.mkdtemp()
    p = Path(d) / "a.mp3"
    p.write_bytes(b"abc")
    return p


class ParseTests(unittest.TestCase):
    def test_words_and_text(self):
        got = deepgram.parse(BODY)
        self.assertEqual(got["text"], "من به خانه رفتم")
        self.assertEqual(got["words"][2], {"text": "خانه", "heard": "خانه", "start": 0.5, "end": 0.9})

    def test_nothing_heard_is_none(self):
        self.assertIsNone(deepgram.parse({"results": {"channels": [{"alternatives": [{"transcript": "", "words": []}]}]}}))
        self.assertIsNone(deepgram.parse({}))


class DeepgramClientTests(unittest.TestCase):
    def test_sends_key_and_audio_to_persian_model(self):
        op = opener_returning(BODY)
        got = deepgram.DeepgramClient("KEY", opener=op).listen(mp3())
        self.assertEqual(got["text"], "من به خانه رفتم")
        req = op.calls[0]
        self.assertIn("language=fa", req.full_url)
        self.assertIn("nova-3", req.full_url)
        self.assertEqual(req.get_header("Authorization"), "Token KEY")
        self.assertEqual(req.data, b"abc")

    def test_network_error_retried_once_then_none(self):
        op = opener_failing()
        self.assertIsNone(deepgram.DeepgramClient("K", opener=op, pause=0).listen(mp3()))
        self.assertEqual(len(op.calls), deepgram.TRIES)

    def test_one_failure_then_success(self):
        op = opener_failing(times=1)
        self.assertIsNotNone(deepgram.DeepgramClient("K", opener=op, pause=0).listen(mp3()))

    def test_no_credit_is_not_retried(self):
        op = opener_failing(code=402)
        self.assertIsNone(deepgram.DeepgramClient("K", opener=op, pause=0).listen(mp3()))
        self.assertEqual(len(op.calls), 1)

    def test_missing_file_is_none(self):
        self.assertIsNone(deepgram.DeepgramClient("K", opener=opener_returning(BODY)).listen(Path("/no/such.mp3")))

    def test_key_never_printed(self):
        import contextlib
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            deepgram.DeepgramClient("SECRETKEY", opener=opener_failing(code=401), pause=0).listen(mp3())
        self.assertNotIn("SECRETKEY", err.getvalue())


class FakeGemini:
    def __init__(self):
        self.calls = []

    def correct_text(self, audio, draft, hint=""):
        self.calls.append(("correct", draft, hint))
        return "اصلاح"

    def transcribe_sentences(self, audio, careful=False, hint=""):
        self.calls.append(("sent", careful, hint))
        return ["S"]

    def align_words(self, audio, text=""):
        self.calls.append(("align", text))
        return [{"text": "g", "heard": "g", "start": 0, "end": 1}]

    def other(self):
        return "delegated"


class FakeDg:
    def __init__(self, result="default", boom=False):
        self.result = deepgram.parse(BODY) if result == "default" else result
        self.boom, self.n = boom, 0

    def listen(self, audio):
        self.n += 1
        if self.boom:
            raise RuntimeError("x")
        return self.result


class HybridTests(unittest.TestCase):
    def test_correct_text_passes_deepgram_text_as_second_opinion(self):
        g = FakeGemini()
        self.assertEqual(HybridClient(g, FakeDg()).correct_text(mp3(), "پیش‌نویس"), "اصلاح")
        self.assertEqual(g.calls[0], ("correct", "پیش‌نویس", "من به خانه رفتم"))

    def test_careful_sentences_get_the_hint(self):
        g = FakeGemini()
        HybridClient(g, FakeDg()).transcribe_careful(mp3())
        self.assertEqual(g.calls[0], ("sent", True, "من به خانه رفتم"))

    def test_deepgram_down_means_gemini_alone(self):
        g = FakeGemini()
        c = HybridClient(g, FakeDg(result=None))
        c.correct_text(mp3(), "d")
        self.assertEqual(g.calls[0][2], "")
        self.assertEqual(c.align_words(mp3(), "من به خانه")[0]["text"], "g")

    def test_deepgram_exception_is_swallowed(self):
        g = FakeGemini()
        self.assertEqual(HybridClient(g, FakeDg(boom=True)).correct_text(mp3(), "d"), "اصلاح")

    def test_word_times_come_from_deepgram_when_it_heard_the_same_speech(self):
        g = FakeGemini()
        rows = HybridClient(g, FakeDg()).align_words(mp3(), "من به خانه رفتم")
        self.assertEqual([r["text"] for r in rows], ["من", "به", "خانه", "رفتم"])
        self.assertEqual(rows[3]["start"], 1.0)
        self.assertFalse([c for c in g.calls if c[0] == "align"])

    def test_word_times_fall_back_to_gemini_when_speech_differs(self):
        g = FakeGemini()
        rows = HybridClient(g, FakeDg()).align_words(mp3(), "کاملاً متن دیگری است که ربطی ندارد")
        self.assertEqual(rows[0]["text"], "g")

    def test_listened_once_per_file(self):
        g, d, p = FakeGemini(), FakeDg(), mp3()
        c = HybridClient(g, d)
        c.correct_text(p, "x")
        c.align_words(p, "من به خانه رفتم")
        self.assertEqual(d.n, 1)

    def test_other_methods_go_to_gemini(self):
        self.assertEqual(HybridClient(FakeGemini(), FakeDg()).other(), "delegated")


class GeminiHintTests(unittest.TestCase):
    def client(self):
        from transcribe import GeminiClient
        seen = []

        def generate(model, contents, config):
            seen.append(contents[0])
            return NS(text='[{"text": "ok", "start": 0, "end": 1}]')
        api = NS(files=NS(upload=lambda file: "F"), models=NS(list=lambda: [], generate_content=generate))
        c = GeminiClient.__new__(GeminiClient)
        c._client, c._models, c._careful_models = api, ["flash"], None
        return c, seen

    def test_hint_reaches_the_prompt_for_text_and_sentences(self):
        c, seen = self.client()
        c.correct_text(Path("a.mp3"), "پیش‌نویس", hint="نظر ماشین دوم")
        self.assertIn("نظر ماشین دوم", seen[0])
        self.assertIn("پیش‌نویس", seen[0])

    def test_no_hint_leaves_prompt_unchanged(self):
        c, seen = self.client()
        c.correct_text(Path("a.mp3"), "پیش‌نویس")
        self.assertNotIn("نظر دوم", seen[0])


class HelperTests(unittest.TestCase):
    def test_words_match_ignores_spelling_of_punctuation_and_halfspace(self):
        self.assertGreater(words_match("می‌خواهم بروم، خانه.", [{"text": "میخواهم"}, {"text": "بروم"}, {"text": "خانه"}]), 0.5)

    def test_hint_text_is_quoted_and_empty_hint_adds_nothing(self):
        self.assertIn("«سلام»", _hint("سلام"))
        self.assertEqual(_hint(""), "")


if __name__ == "__main__":
    unittest.main()

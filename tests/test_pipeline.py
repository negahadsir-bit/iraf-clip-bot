import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pipeline
from media import InputError
from models import Sentence
from pipeline import Deps, process
from retry import BusyError
from select_clips import SelectionError
from transcribe import QuotaError, TranscriptionError

SENTS = [Sentence(f"جمله {i}.", i * 10.0, i * 10.0 + 9) for i in range(20)]
MSG = {"chat": {"id": 1}, "text": "x"}


class Sel:
    def generate_json(self, prompt):
        return [{"rank": 1, "start": 10, "end": 50, "reason": "چون خوب است"}]


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.deps = Deps(tg=None, transcribe_client=None, select_client=Sel(),
                         workdir=Path(self.tmp.name), rules="R")

    def run_with(self, transcribe_effect=None, fetch_effect=None):
        with mock.patch.object(pipeline, "resolve_input", return_value=object()), \
             mock.patch.object(pipeline, "fetch_input", side_effect=fetch_effect, return_value=Path("in")), \
             mock.patch.object(pipeline, "to_audio", return_value=Path("a.mp3")), \
             mock.patch.object(pipeline, "transcribe",
                               side_effect=transcribe_effect, return_value=SENTS):
            return process(MSG, self.deps)

    def test_happy_path(self):
        out = self.run_with()
        text = "\n".join(out)
        self.assertIn("1)", text)
        self.assertIn("0:10", text)

    def test_no_speech(self):
        out = self.run_with(transcribe_effect=TranscriptionError("e"))
        self.assertEqual(out, ["هیچ گفتاری در فایل پیدا نشد."])

    def test_quota(self):
        out = self.run_with(transcribe_effect=QuotaError("429"))
        self.assertEqual(out, ["سهمیه‌ی رایگان Gemini پر شده؛ کمی بعد دوباره بفرست."])

    def test_input_error_text_passthrough(self):
        out = self.run_with(fetch_effect=InputError("پیام ویژه"))
        self.assertEqual(out, ["پیام ویژه"])

    def test_busy(self):
        out = self.run_with(transcribe_effect=BusyError("x"))
        self.assertEqual(out, ["Gemini الان شلوغ است؛ چند دقیقه بعد دوباره بفرست."])

    def test_selection_error(self):
        with mock.patch.object(pipeline, "select_clips", side_effect=SelectionError("x")):
            out = self.run_with()
        self.assertEqual(out, ["انتخاب کلیپ‌ها ناموفق بود؛ دوباره امتحان کن."])

    def test_unexpected_error_hides_details(self):
        out = self.run_with(transcribe_effect=RuntimeError("SECRET-TOKEN-123"))
        self.assertEqual(len(out), 1)
        self.assertNotIn("SECRET", out[0])


if __name__ == "__main__":
    unittest.main()

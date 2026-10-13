import subprocess
import tempfile
import unittest
from pathlib import Path
from models import Word, Sentence
from transcribe import transcribe, QuotaError, TranscriptionError


def make_silence(path: Path, seconds: int):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                    "anullsrc=r=16000:cl=mono", "-t", str(seconds), "-b:a", "24k",
                    str(path)], check=True)


class FakeClient:
    def __init__(self, words=None, sentences=None, error=None):
        self.words, self.sentences, self.error = words, sentences, error
        self.word_calls = 0

    def transcribe_words(self, audio):
        self.word_calls += 1
        if self.error:
            raise self.error
        return self.words

    def transcribe_sentences(self, audio):
        return self.sentences


class TranscribeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.audio = self.dir / "a.mp3"
        make_silence(self.audio, 3)

    def test_uses_word_times_when_available(self):
        c = FakeClient(words=[Word("سلام", 1.0, 1.4), Word("دنیا.", 1.5, 2.0)])
        out = transcribe(self.audio, c, workdir=self.dir)
        self.assertEqual([s.text for s in out], ["سلام دنیا."])
        self.assertEqual((out[0].start, out[0].end), (1.0, 2.0))

    def test_falls_back_to_sentence_times_when_no_word_times(self):
        c = FakeClient(words=None, sentences=[Sentence("جمله.", 1.0, 2.0)])
        out = transcribe(self.audio, c, workdir=self.dir)
        self.assertEqual(out, [Sentence("جمله.", 1.0, 2.0)])

    def test_empty_result_raises_transcription_error(self):
        with self.assertRaises(TranscriptionError):
            transcribe(self.audio, FakeClient(words=[], sentences=[]), workdir=self.dir)

    def test_quota_error_is_recognised(self):
        c = FakeClient(error=RuntimeError("429 RESOURCE_EXHAUSTED: quota"))
        with self.assertRaises(QuotaError):
            transcribe(self.audio, c, workdir=self.dir)

    def test_long_audio_is_chunked_and_times_are_offset(self):
        long_audio = self.dir / "long.mp3"
        make_silence(long_audio, 25)
        c = FakeClient(words=[Word("الف.", 1.0, 1.4)])
        out = transcribe(long_audio, c, workdir=self.dir, chunk_seconds=10)
        self.assertEqual(c.word_calls, 3)
        self.assertEqual([round(s.start) for s in out], [1, 11, 21])


if __name__ == "__main__":
    unittest.main()

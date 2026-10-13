import json
import os
import subprocess
import tempfile
from pathlib import Path

from models import Sentence, Word
from retry import call_with_fallback, models_from_env
from timeline import fix_word_times, words_to_sentences


class QuotaError(Exception):
    pass


class TranscriptionError(Exception):
    pass


def _split(audio: Path, workdir: Path, chunk_seconds: int) -> list[Path]:
    out = workdir / "chunks"
    out.mkdir(parents=True, exist_ok=True)
    pattern = out / "c%03d.mp3"
    r = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(audio), "-f", "segment",
         "-segment_time", str(chunk_seconds), "-c", "copy", "-reset_timestamps", "1",
         str(pattern)], capture_output=True)
    if r.returncode != 0:
        raise TranscriptionError("ffmpeg split failed")
    return sorted(out.glob("c*.mp3"))


def transcribe(audio: Path, client, workdir: Path = None, chunk_seconds: int = 600) -> list[Sentence]:
    workdir = Path(workdir or tempfile.mkdtemp())
    result: list[Sentence] = []
    for i, chunk in enumerate(_split(audio, workdir, chunk_seconds)):
        try:
            words = client.transcribe_words(chunk)
            if words:
                sentences = words_to_sentences(fix_word_times(words))
            else:
                sentences = client.transcribe_sentences(chunk) or []
        except Exception as e:  # noqa: BLE001
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                raise QuotaError(str(e)) from e
            raise
        off = i * chunk_seconds
        result += [Sentence(s.text, s.start + off, s.end + off) for s in sentences]
    if not result:
        raise TranscriptionError("empty transcript")
    return result


_PROMPT_WORDS = (
    "این فایل صوتی فارسی را کلمه به کلمه بنویس. فقط JSON برگردان: "
    '[{"text": "...", "start": ثانیه, "end": ثانیه}, ...] با زمان واقعی هر کلمه از ابتدای فایل. '
    "علائم نقطه، ؟ و ! را در پایان جمله‌ها بگذار.")
_PROMPT_SENT = (
    "این فایل صوتی فارسی را جمله به جمله بنویس. فقط JSON برگردان: "
    '[{"text": "...", "start": ثانیه, "end": ثانیه}, ...] با زمان شروع و پایان هر جمله از ابتدای فایل.')


class GeminiClient:
    """Real client; google-genai imported lazily (not unit-tested)."""

    def __init__(self, api_key: str, model: str = None):
        from google import genai
        self._genai = genai
        self._client = genai.Client(api_key=api_key)
        self._models = [model] if model else models_from_env()

    def _ask(self, audio: Path, prompt: str) -> list[dict]:
        f = self._client.files.upload(file=str(audio))
        resp = call_with_fallback(
            lambda m: self._client.models.generate_content(
                model=m, contents=[prompt, f],
                config={"response_mime_type": "application/json"}),
            self._models)
        try:
            data = json.loads(resp.text)
        except (ValueError, TypeError):
            return []
        return [d for d in data if isinstance(d, dict) and "text" in d] if isinstance(data, list) else []

    def transcribe_words(self, audio: Path):
        rows = self._ask(audio, _PROMPT_WORDS)
        if not rows:
            return None
        try:
            return [Word(str(r["text"]), float(r["start"]), float(r["end"])) for r in rows]
        except (KeyError, TypeError, ValueError):
            return None

    def transcribe_sentences(self, audio: Path):
        rows = self._ask(audio, _PROMPT_SENT)
        out = []
        for r in rows:
            try:
                out.append(Sentence(str(r["text"]), float(r["start"]), float(r["end"])))
            except (KeyError, TypeError, ValueError):
                continue
        return out

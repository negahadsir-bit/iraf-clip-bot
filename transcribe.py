import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

from models import Sentence, Word
from retry import BusyError, QuotaError, call_with_fallback, models_from_env
from timeline import fix_word_times, words_to_sentences


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


def _one(client, chunk: Path) -> list[Sentence]:
    try:
        words = client.transcribe_words(chunk)
        if words:
            return words_to_sentences(fix_word_times(words))
        return client.transcribe_sentences(chunk) or []
    except BusyError:
        raise
    except Exception as e:  # noqa: BLE001
        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
            raise QuotaError(str(e)) from e
        raise


def transcribe(audio: Path, client, workdir: Path = None, chunk_seconds: int = 300,
               progress=None, on_skip=None, sleep=time.sleep,
               retry_wait: float = 30.0) -> list[Sentence]:
    """Transcribe in chunks. A chunk that stays busy is retried once at the end
    and then skipped (reported via on_skip) so one bad chunk never loses the rest."""
    workdir = Path(workdir or tempfile.mkdtemp())
    chunks = _split(audio, workdir, chunk_seconds)
    done: dict[int, list[Sentence]] = {}
    busy: list[int] = []
    last_busy = None
    finished = 0

    def finish():
        nonlocal finished
        finished += 1
        if progress:
            progress(finished, len(chunks))

    for i, chunk in enumerate(chunks):
        try:
            done[i] = _one(client, chunk)
            finish()
        except BusyError as e:
            busy.append(i)
            last_busy = e
    if busy:
        sleep(retry_wait)
    for i in busy:
        try:
            done[i] = _one(client, chunks[i])
        except BusyError as e:
            last_busy = e
            if on_skip:
                on_skip(i + 1, len(chunks))
        finish()
    if busy and not any(done.values()):
        raise last_busy
    result = [Sentence(s.text, s.start + i * chunk_seconds, s.end + i * chunk_seconds)
              for i in sorted(done) for s in done[i]]
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
        from google.genai import types
        self._client = genai.Client(
            api_key=api_key, http_options=types.HttpOptions(timeout=180_000))
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
        # Word-level output is too long for the API (connections drop), so the
        # real client uses sentence-level times only; see transcribe_sentences.
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

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from models import Sentence, Word
from retry import BusyError, QuotaError, call_with_fallback, models_from_env
from timeline import fix_word_times, parse_seconds, words_to_sentences


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
               retry_wait: float = 30.0, workers: int = 3) -> list[Sentence]:
    """Transcribe in chunks. A chunk that stays busy is retried once at the end
    and then skipped (reported via on_skip) so one bad chunk never loses the rest."""
    workdir = Path(workdir or tempfile.mkdtemp())
    chunks = _split(audio, workdir, chunk_seconds)
    done: dict[int, list[Sentence]] = {}
    busy: list[int] = []
    last_busy = None
    finished = 0
    lock = threading.Lock()

    def finish():
        nonlocal finished
        with lock:
            finished += 1
            n = finished
        if progress:
            progress(n, len(chunks))

    def work(i):
        try:
            done[i] = _one(client, chunks[i])
            finish()
        except QuotaError:
            raise
        except Exception as e:  # noqa: BLE001 - one bad chunk must not lose the rest
            print(f"chunk {i + 1} failed: {type(e).__name__}: {str(e)[:200]}",
                  file=sys.stderr, flush=True)
            with lock:
                busy.append(i)
                nonlocal last_busy
                last_busy = e if isinstance(e, BusyError) else BusyError(str(e))

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for f in [pool.submit(work, i) for i in range(len(chunks))]:
            f.result()  # re-raises QuotaError and other hard failures
    busy.sort()
    if busy:
        sleep(retry_wait)
    for i in busy:
        try:
            done[i] = _one(client, chunks[i])
        except QuotaError:
            raise
        except Exception as e:  # noqa: BLE001
            last_busy = e if isinstance(e, BusyError) else BusyError(str(e))
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
    "این فایل صوتی فارسی را جمله به جمله بنویس؛ هر جمله کوتاه باشد (حداکثر حدود ۱۵ کلمه) و جمله‌ی طولانی را "
    "به چند جمله بشکن. فقط JSON برگردان: "
    '[{"text": "...", "start": ثانیه, "end": ثانیه}, ...] با زمان دقیق شروع و پایان هر جمله از ابتدای فایل، '
    "به‌صورت عدد ثانیه‌ی اعشاری (مثلاً 83.5) و نه دقیقه:ثانیه.")


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
                out.append(Sentence(str(r["text"]), parse_seconds(r["start"]), parse_seconds(r["end"])))
            except (KeyError, TypeError, ValueError):
                continue
        return out

"""Gemini with Deepgram beside it.

Deepgram listens to each short clip too. Its text goes to Gemini as a second opinion (Gemini
still listens and decides, so a wrong guess from Deepgram is never copied blindly), and its
acoustic word times replace Gemini's estimated ones. Without Deepgram, or when it fails,
everything falls back to Gemini alone."""
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

MIN_MATCH = 0.4   # below this Deepgram heard something else than the caption text: use Gemini's times
_ZW = dict.fromkeys(map(ord, "‌‍‏‎"), None)


def _norm(w: str) -> str:
    return re.sub(r"[^\w]", "", w.translate(_ZW).replace("ي", "ی").replace("ك", "ک"))


def words_match(text: str, words: list[dict]) -> float:
    a = [x for x in (_norm(w) for w in text.split()) if x]
    b = [x for x in (_norm(w["text"]) for w in words) if x]
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b, autojunk=False).ratio()


class HybridClient:
    """Drop-in for GeminiClient: unknown methods go to Gemini."""

    def __init__(self, gemini, deepgram):
        self._g = gemini
        self._d = deepgram
        self._seen = {}

    def __getattr__(self, name):
        if name.startswith("__") or name in ("_g", "_d", "_seen"):
            raise AttributeError(name)
        return getattr(self._g, name)

    def _heard(self, audio: Path):
        """Deepgram's reading of this clip, asked once per file."""
        p = Path(audio)
        try:
            st = p.stat()
            key = (str(p), st.st_size, st.st_mtime_ns)
        except OSError:
            return None
        if key not in self._seen:
            try:
                self._seen[key] = self._d.listen(p)
            except Exception as e:  # noqa: BLE001 - never fatal
                print(f"second opinion unavailable: {type(e).__name__}", file=sys.stderr, flush=True)
                self._seen[key] = None
        return self._seen[key]

    def correct_text(self, audio: Path, draft: str) -> str:
        h = self._heard(audio)
        return self._g.correct_text(audio, draft, hint=h["text"] if h else "")

    def transcribe_careful(self, audio: Path):
        h = self._heard(audio)
        return self._g.transcribe_sentences(audio, careful=True, hint=h["text"] if h else "")

    def align_words(self, audio: Path, text: str = "") -> list[dict]:
        h = self._heard(audio) if text else None
        if h and words_match(text, h["words"]) >= MIN_MATCH:
            print(f"word times: deepgram ({len(h['words'])} words)", file=sys.stderr, flush=True)
            return [dict(w) for w in h["words"]]
        print("word times: gemini", file=sys.stderr, flush=True)
        return self._g.align_words(audio, text)

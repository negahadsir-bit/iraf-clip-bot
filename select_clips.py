import json
import sys
from dataclasses import replace
from categories import focus_note
from models import Clip, Sentence
from retry import BusyError, QuotaError, call_with_fallback, models_from_env

MAX_CLIPS = 12
EXTRA = 4  # ask for spare candidates: some get dropped (overlap, length)
WORDS_PER_SEC = 2.6
MIN_DUR, TARGET_MIN, MAX_DUR = 20.0, 35.0, 75.0


class SelectionError(Exception):
    pass


def _task(want: int) -> str:
    return (
        f"تو دستیار انتخاب کلیپ از مصاحبه‌های بلند هستی. بر اساس قوانین بالا، حداکثر {want} بازه‌ی "
        "مناسب برای کلیپ حدود یک‌دقیقه‌ای پیشنهاد بده، از بهترین به ضعیف‌تر، و تا جای ممکن در "
        f"همان {want} مورد پر کن، پخش‌شده در کل مصاحبه (نه فقط ابتدا)؛ اگر چیز خوبی نیست "
        "فهرست خالی برگردان. هر جمله با شماره‌ی [n] آمده. فقط JSON برگردان: "
        '[{"rank": 1, "from": شماره‌ی جمله‌ی شروع, "to": شماره‌ی جمله‌ی پایان, "reason": "دلیل کوتاه به فارسی"}]. '
        "from و to شماره‌ی جمله‌اند (نه زمان) و to ≥ from.")


def _dur(sentences: list[Sentence], a: int, b: int) -> float:
    """Timestamps are approximate, so never trust them below what the words need."""
    words = sum(len(s.text.split()) for s in sentences[a:b + 1])
    return max(sentences[b].end - sentences[a].start, words / WORDS_PER_SEC)


def _numbered(sentences: list[Sentence]) -> str:
    lines = []
    for i, s in enumerate(sentences):
        sec = int(s.start)
        lines.append(f"[{i}] {sec // 60}:{sec % 60:02d} {s.text}")
    return "\n".join(lines)


def select_clips(sentences: list[Sentence], rules: str, client,
                 want: int = 10, focus=(), examples: str = "") -> list[Clip]:
    note = focus_note(focus)
    prompt = "\n\n".join(part for part in (
        rules, note, examples, _task(want + EXTRA),
        f"جمله‌ها (شماره، زمان، متن):\n{_numbered(sentences)}") if part)
    try:
        raw = client.generate_json(prompt)
    except (BusyError, QuotaError):
        raise
    except Exception as e:  # noqa: BLE001
        raise SelectionError(str(e)) from e
    if not isinstance(raw, list):
        raise SelectionError("not a list")
    n = len(sentences)
    clips = []
    drops = {"bad_index": 0, "bad_length": 0, "overlap": 0}
    for d in sorted(raw, key=lambda d: d.get("rank", 0) if isinstance(d, dict) else 0):
        try:
            rank, a, b = int(d["rank"]), int(d["from"]), int(d["to"])
            reason = str(d.get("reason", ""))
        except (KeyError, TypeError, ValueError, AttributeError):
            raise SelectionError("malformed item")
        if not (0 <= a <= b < n):
            drops["bad_index"] += 1
            continue
        while _dur(sentences, a, b) < TARGET_MIN and b + 1 < n:
            b += 1  # the model cannot see durations: grow short picks sentence by sentence
        while _dur(sentences, a, b) > MAX_DUR and b > a:
            b -= 1
        c = Clip(rank, sentences[a].start, sentences[b].end, reason,
                 " ".join(s.text for s in sentences[a:b + 1]))
        if not (MIN_DUR <= _dur(sentences, a, b) <= MAX_DUR):
            drops["bad_length"] += 1
            continue
        if any(c.start < k.end and k.start < c.end for k in clips):
            drops["overlap"] += 1
            continue
        clips.append(c)
    print(f"selection: raw={len(raw)} kept={len(clips)} "
          + " ".join(f"{k}={v}" for k, v in drops.items())
          + f" sentences={n}", file=sys.stderr, flush=True)
    print(f"selection raw json: {json.dumps(raw, ensure_ascii=False)[:1500]}",
          file=sys.stderr, flush=True)
    return [replace(c, rank=i) for i, c in enumerate(clips[:min(want, MAX_CLIPS)], 1)]


class GeminiTextClient:
    def __init__(self, api_key: str, model: str = None):
        from google import genai
        from google.genai import types
        self._client = genai.Client(
            api_key=api_key, http_options=types.HttpOptions(timeout=180_000))
        self._models = [model] if model else models_from_env()

    def generate_json(self, prompt: str) -> list[dict]:
        resp = call_with_fallback(
            lambda m: self._client.models.generate_content(
                model=m, contents=prompt,
                config={"response_mime_type": "application/json"}),
            self._models)
        return json.loads(resp.text)


class FallbackClient:
    """Try the primary client; if it fails for any reason, use the secondary."""

    def __init__(self, primary, secondary):
        self.primary, self.secondary = primary, secondary

    def generate_json(self, prompt: str):
        try:
            return self.primary.generate_json(prompt)
        except Exception as e:  # noqa: BLE001
            print(f"primary selection client failed ({type(e).__name__}); using fallback",
                  file=sys.stderr, flush=True)
            return self.secondary.generate_json(prompt)


def make_select_client(env, gemini_key: str):
    """DeepSeek (falling back to Gemini) when DEEPSEEK_API_KEY is set, otherwise Gemini."""
    key = (env.get("DEEPSEEK_API_KEY") or "").strip()
    if key:
        from deepseek import DeepSeekTextClient
        return FallbackClient(DeepSeekTextClient(key), GeminiTextClient(gemini_key))
    return GeminiTextClient(gemini_key)

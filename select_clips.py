import json
from models import Clip, Sentence
from retry import BusyError, QuotaError, call_with_fallback, models_from_env
from timeline import to_transcript

MAX_CLIPS = 12
MIN_DUR, MAX_DUR = 15.0, 90.0


class SelectionError(Exception):
    pass


def _task(want: int) -> str:
    return (
        f"تو دستیار انتخاب کلیپ از مصاحبه‌های بلند هستی. بر اساس قوانین بالا، حداکثر {want} بازه‌ی "
        "مناسب برای کلیپ حدود یک‌دقیقه‌ای پیشنهاد بده، از بهترین به ضعیف‌تر؛ اگر چیز خوبی نیست "
        "فهرست خالی برگردان. فقط JSON برگردان: "
        '[{"rank": 1, "start": ثانیه, "end": ثانیه, "reason": "دلیل کوتاه به فارسی"}]. '
        "start و end باید از زمان‌های متن زیر باشند.")


def select_clips(sentences: list[Sentence], rules: str, client,
                 want: int = 10) -> list[Clip]:
    prompt = f"{rules}\n\n{_task(want)}\n\nمتن با زمان (دقیقه:ثانیه):\n{to_transcript(sentences)}"
    try:
        raw = client.generate_json(prompt)
    except (BusyError, QuotaError):
        raise
    except Exception as e:  # noqa: BLE001
        raise SelectionError(str(e)) from e
    if not isinstance(raw, list):
        raise SelectionError("not a list")
    end_of_episode = sentences[-1].end if sentences else 0.0
    clips = []
    for d in raw:
        try:
            c = Clip(int(d["rank"]), float(d["start"]), float(d["end"]), str(d.get("reason", "")))
        except (KeyError, TypeError, ValueError, AttributeError):
            raise SelectionError("malformed item")
        dur = c.end - c.start
        if c.end <= c.start or not (0 <= c.start < end_of_episode) or not (MIN_DUR <= dur <= MAX_DUR):
            continue
        clips.append(c)
    clips.sort(key=lambda c: c.rank)
    return clips[:min(want, MAX_CLIPS)]


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

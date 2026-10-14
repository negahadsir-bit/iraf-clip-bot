"""«words» mode: a video/audio sent with the caption «words» + the clip text gets
word-by-word times from Gemini, saved as memory/words/<message_id>.json (text only;
the media itself is never stored). Used to sync subtitles for the video templates."""
import json
import re
import sys
from pathlib import Path

from media import InputError, fetch_input, resolve_input, to_audio
from transcribe import audio_seconds

_TRIGGER = re.compile(r"(?is)^\s*words(?=\s|$)\s*(.*)$")
_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
FAILED = "زمان‌یابی کلمه‌ها ناموفق بود؛ دوباره بفرست."


def words_text(message: dict) -> str | None:
    """The clip text when the caption starts with «words»; None for any other message."""
    m = _TRIGGER.match(message.get("caption") or "")
    return m.group(1).strip() if m else None


def run_words(message: dict, text: str, tg, client, workdir: Path, memory_dir: Path,
              fetch=fetch_input, to_audio=to_audio, seconds=audio_seconds) -> None:
    chat_id = message["chat"]["id"]
    try:
        tg.send_message(chat_id, "⏳ در حال زمان‌یابی کلمه‌ها…")
        src = fetch(resolve_input(message), tg, workdir)
        audio = to_audio(src, workdir / "words_audio.mp3")
        rows = client.align_words(audio, text)
        if not rows:
            raise ValueError("empty")
        out = Path(memory_dir) / "words"
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{message.get('message_id', 0)}.json").write_text(
            json.dumps({"text": text, "duration": seconds(audio), "words": rows},
                       ensure_ascii=False, indent=1), encoding="utf-8")
        tg.send_message(chat_id, f"✅ زمان {str(len(rows)).translate(_DIGITS)} کلمه ذخیره شد.")
    except InputError as e:
        tg.send_message(chat_id, str(e))
    except Exception as e:  # noqa: BLE001 - always answer the user
        print(f"words mode failed: {type(e).__name__}: {str(e)[:200]}", file=sys.stderr, flush=True)
        tg.send_message(chat_id, FAILED)

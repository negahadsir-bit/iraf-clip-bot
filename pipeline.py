import sys
import traceback
from dataclasses import dataclass
from pathlib import Path

from formatting import format_clip
from media import InputError, fetch_input, resolve_input, to_audio
from retry import BusyError, QuotaError
from select_clips import SelectionError, select_clips
from snap import snap_clips
from transcribe import TranscriptionError, transcribe

QUOTA = "سهمیه‌ی رایگان Gemini پر شده؛ کمی بعد دوباره بفرست."
NO_SPEECH = "هیچ گفتاری در فایل پیدا نشد."
SELECTION_FAILED = "انتخاب کلیپ‌ها ناموفق بود؛ دوباره امتحان کن."
BUSY = "Gemini الان شلوغ است؛ چند دقیقه بعد دوباره بفرست."
GENERIC = "مشکلی پیش آمد؛ کمی بعد دوباره امتحان کن."


@dataclass
class Deps:
    tg: object
    transcribe_client: object
    select_client: object
    workdir: Path
    rules: str


def _bar(done: int, total: int, width: int = 10) -> str:
    filled = round(width * done / total)
    return "▓" * filled + "░" * (width - filled)


class _Progress:
    """One status message in the chat, edited as work advances (best effort)."""

    def __init__(self, message: dict, deps: Deps):
        self._chat_id = message.get("chat", {}).get("id")
        self._tg = deps.tg
        self._msg_id = None

    def _show(self, text: str) -> None:
        if self._chat_id is None or self._tg is None:
            return
        try:
            if self._msg_id is None:
                self._msg_id = self._tg.send_message(self._chat_id, text)
            else:
                self._tg.edit_message(self._chat_id, self._msg_id, text)
        except Exception:  # noqa: BLE001
            pass

    def __call__(self, done: int, total: int) -> None:
        print(f"transcribed chunk {done}/{total}", file=sys.stderr, flush=True)
        self._show(f"⏳ {_bar(done, total)} {round(100 * done / total)}%  (تکه {done} از {total})")

    def selecting(self) -> None:
        self._show("✍️ متن کامل شد؛ در حال انتخاب بهترین برش‌ها…")


def process(message: dict, deps: Deps) -> list[str]:
    chat_id = message.get("chat", {}).get("id")
    progress = _Progress(message, deps)
    unsent: list[str] = []
    try:
        ref = resolve_input(message)
        src = fetch_input(ref, deps.tg, deps.workdir)
        audio = to_audio(src, deps.workdir / "audio.mp3")
        sentences = transcribe(audio, deps.transcribe_client, workdir=deps.workdir,
                               progress=progress)
        progress.selecting()
        clips = snap_clips(select_clips(sentences, deps.rules, deps.select_client), sentences)
        for clip in clips:
            text = format_clip(clip, sentences)
            try:
                deps.tg.send_message(chat_id, text)
            except Exception:  # noqa: BLE001 - keep the clip, return it at the end
                unsent.append(text)
        if not clips:
            return ["هیچ برش مناسبی پیدا نشد."]
        return unsent + [f"✅ تمام شد: {len(clips)} پیشنهاد برش"]
    except InputError as e:
        return [str(e)]
    except BusyError as e:
        print(f"busy: {e}", file=sys.stderr)
        return unsent + [BUSY]
    except QuotaError as e:
        print(f"quota: {e}", file=sys.stderr)
        return unsent + [QUOTA]
    except TranscriptionError:
        return unsent + [NO_SPEECH]
    except SelectionError:
        return unsent + [SELECTION_FAILED]
    except Exception:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
        return unsent + [GENERIC]

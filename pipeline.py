import sys
import traceback
from dataclasses import dataclass
from pathlib import Path

from formatting import format_messages
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


def _progress_reporter(message: dict, deps: Deps):
    chat_id = message.get("chat", {}).get("id")
    state = {"msg_id": None}

    def report(done: int, total: int) -> None:
        print(f"transcribed chunk {done}/{total}", file=sys.stderr, flush=True)
        if chat_id is None or deps.tg is None:
            return
        text = f"⏳ {_bar(done, total)} {round(100 * done / total)}%  (تکه {done} از {total})"
        try:
            if state["msg_id"] is None:
                state["msg_id"] = deps.tg.send_message(chat_id, text)
            else:
                deps.tg.edit_message(chat_id, state["msg_id"], text)
        except Exception:  # noqa: BLE001 - progress is best effort
            pass
    return report


def process(message: dict, deps: Deps) -> list[str]:
    try:
        ref = resolve_input(message)
        src = fetch_input(ref, deps.tg, deps.workdir)
        audio = to_audio(src, deps.workdir / "audio.mp3")
        sentences = transcribe(audio, deps.transcribe_client, workdir=deps.workdir,
                               progress=_progress_reporter(message, deps))
        clips = select_clips(sentences, deps.rules, deps.select_client)
        clips = snap_clips(clips, sentences)
        return format_messages(clips, sentences, sentences[-1].end)
    except InputError as e:
        return [str(e)]
    except BusyError as e:
        print(f"busy: {e}", file=sys.stderr)
        return [BUSY]
    except QuotaError as e:
        print(f"quota: {e}", file=sys.stderr)
        return [QUOTA]
    except TranscriptionError:
        return [NO_SPEECH]
    except SelectionError:
        return [SELECTION_FAILED]
    except Exception:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
        return [GENERIC]

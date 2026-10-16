import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import os
TG_LIMIT = (2000 if os.environ.get("TELEGRAM_API_URL") else 20) * 1024 * 1024
_MEDIA_KEYS = ("audio", "voice", "video", "video_note", "document")
_DRIVE_RE = re.compile(r"drive\.google\.com/(?:file/d/|open\?id=|uc\?id=)([A-Za-z0-9_-]+)")

TOO_BIG = ("فایل بیشتر از ۲۰ مگابایت است و ربات تلگرام نمی‌تواند آن را بگیرد. "
           "لینک Drive (با دسترسی Anyone with the link) بفرست یا فایل را فشرده کن.")
NO_INPUT = "یک فایل صوتی/ویدیویی یا لینک Drive بفرست."
PRIVATE_DRIVE = ("لینک Drive قابل دانلود نبود. در Drive روی Share بزن و دسترسی را "
                 "روی Anyone with the link بگذار، بعد دوباره بفرست.")
BAD_MEDIA = "فایل صدایی ندارد یا خراب است."


class InputError(Exception):
    """Message is Persian and safe to show to the user."""


@dataclass(frozen=True)
class InputRef:
    kind: str  # "telegram" | "drive"
    ref: str


def extract_drive_id(text: str) -> str | None:
    m = _DRIVE_RE.search(text or "")
    return m.group(1) if m else None


def resolve_input(message: dict) -> InputRef:
    media = next((message[k] for k in _MEDIA_KEYS if k in message), None)
    if media is not None and media.get("file_size", 0) <= TG_LIMIT:
        return InputRef("telegram", media["file_id"])
    drive = extract_drive_id(f"{message.get('text', '')} {message.get('caption', '')}")
    if drive:
        return InputRef("drive", drive)
    raise InputError(TOO_BIG if media is not None else NO_INPUT)


def _looks_like_html(path: Path) -> bool:
    head = path.read_bytes()[:256].lower()
    return b"<!doctype html" in head or b"<html" in head


def fetch_input(ref: InputRef, tg, workdir: Path, downloader=None) -> Path:
    if ref.kind == "telegram":
        file_path = tg.get_file_path(ref.ref)
        dest = workdir / ("input" + Path(file_path).suffix)
        tg.download(file_path, dest)
        return dest
    if downloader is None:
        import gdown
        downloader = gdown.download
    dest = workdir / "input.bin"
    try:
        downloader(f"https://drive.google.com/uc?id={ref.ref}", str(dest), quiet=True)
    except Exception:
        raise InputError(PRIVATE_DRIVE) from None
    if not dest.exists() or dest.stat().st_size == 0 or _looks_like_html(dest):
        raise InputError(PRIVATE_DRIVE)
    return dest


def to_audio(src: Path, dst: Path) -> Path:
    proc = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vn", "-ac", "1",
         "-ar", "16000", "-b:a", "24k", str(dst)],
        capture_output=True)
    if proc.returncode != 0 or not dst.exists() or dst.stat().st_size == 0:
        raise InputError(BAD_MEDIA)
    return dst

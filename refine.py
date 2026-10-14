import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

from align import locate
from models import Clip
from retry import QuotaError

MIN_LEN, MAX_LEN = 18.0, 76.0
PADS = (25.0, 100.0)  # first look close by, then much wider


def _cut(audio: Path, start: float, length: float, dest: Path) -> Path:
    r = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.2f}", "-t", f"{length:.2f}",
         "-i", str(audio), "-ac", "1", "-ar", "16000", "-b:a", "48k", str(dest)],
        capture_output=True)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg cut failed")
    return dest


def _heard_text(window, start: float, end: float, fallback: str) -> str:
    """What the short, fresh transcription hears between the edges. The first pass can drop
    words, so the shown dialogue would look shorter than the seconds; keep the fuller one."""
    inside = []
    for s in window:
        length = max(s.end - s.start, 0.01)
        overlap = min(s.end, end) - max(s.start, start)
        if overlap / length >= 0.5:
            inside.append(s.text)
    heard = " ".join(inside)
    return heard if len(heard.split()) > len(fallback.split()) else fallback


def refine_one(clip: Clip, audio: Path, total: float, client, workdir: Path) -> Clip:
    """Re-transcribe only the clip's surroundings (short audio keeps timestamps accurate)
    and move the clip edges to where its words really are."""
    for pad in PADS:
        w0 = max(0.0, clip.start - pad)
        w1 = min(total, clip.end + pad)
        dest = workdir / f"win_{clip.rank}_{int(pad)}.mp3"
        window = client.transcribe_sentences(_cut(audio, w0, w1 - w0, dest))
        found = locate(clip.text, window, clip.start - w0) if window else None
        if found and MIN_LEN <= found[1] - found[0] <= MAX_LEN:
            return replace(clip, start=w0 + found[0], end=w0 + found[1],
                           text=_heard_text(window, found[0], found[1], clip.text))
    return clip


def refine_clips(clips: list[Clip], audio: Path, total: float, client, workdir: Path,
                 workers: int = 3) -> list[Clip]:
    def work(c: Clip) -> Clip:
        try:
            return refine_one(c, audio, total, client, workdir)
        except QuotaError:
            raise
        except Exception as e:  # noqa: BLE001 - a failed refinement keeps the original clip
            print(f"refine clip {c.rank} skipped: {type(e).__name__}", file=sys.stderr, flush=True)
            return c

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(work, c) for c in clips]
        out = []
        for c, f in zip(clips, futures):
            try:
                out.append(f.result())
            except QuotaError:
                out.append(c)
    moved = sum(1 for a, b in zip(clips, out) if (a.start, a.end) != (b.start, b.end))
    print(f"refine: {moved}/{len(clips)} clips re-timed", file=sys.stderr, flush=True)
    return out

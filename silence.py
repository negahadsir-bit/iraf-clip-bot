import re
import subprocess
from pathlib import Path

from dataclasses import replace

from models import Clip

MIN_CLIP = 20.0
_START = re.compile(r"silence_start: (-?\d+(?:\.\d+)?)")
_END = re.compile(r"silence_end: (-?\d+(?:\.\d+)?)")


def detect_silences(audio: Path, noise_db: int = -35, min_len: float = 0.35) -> list[tuple[float, float]]:
    """(start, end) of every pause in the audio, via ffmpeg silencedetect."""
    r = subprocess.run(
        ["ffmpeg", "-nostats", "-v", "info", "-i", str(audio), "-af",
         f"silencedetect=noise={noise_db}dB:d={min_len}", "-f", "null", "-"],
        capture_output=True, text=True)
    out, start = [], None
    for line in r.stderr.splitlines():
        m = _START.search(line)
        if m:
            start = max(0.0, float(m.group(1)))
            continue
        m = _END.search(line)
        if m and start is not None:
            out.append((start, float(m.group(1))))
            start = None
    return out


def _nearest(value: float, candidates: list[float], window: float):
    near = [c for c in candidates if abs(c - value) <= window]
    return min(near, key=lambda c: abs(c - value)) if near else None


def snap_to_silence(clips: list[Clip], silences: list[tuple[float, float]],
                    window: float = 4.0) -> list[Clip]:
    """Pull each clip start to the nearest speech onset and each end to the nearest
    pause start (within window seconds), correcting small timestamp errors."""
    onsets = [e for _, e in silences]
    pauses = [s for s, _ in silences]
    out = []
    for c in clips:
        start = _nearest(c.start, onsets, window)
        end = _nearest(c.end, pauses, window)
        start = c.start if start is None else start
        end = c.end if end is None else end
        if end - start < MIN_CLIP:
            start, end = c.start, c.end
        out.append(replace(c, start=start, end=end))
    return out

import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

from align import locate_edge, normalize
from models import Clip
from refine import _cut
from retry import QuotaError

EDGE_WORDS = 6
NEAR, FAR = 15.0, 45.0  # listen this far around an edge, then much wider
LEAD, TAIL = 0.2, 0.3   # breathing room so the first and last word are not clipped
MIN_LEN, MAX_LEN = 18.0, 76.0


def _heard_edge(words, side, t, audio, total, client, workdir, rank):
    """Where the edge words really are, from short windows (short audio = accurate times)."""
    for pad in (NEAR, FAR):
        w0, w1 = max(0.0, t - pad), min(total, t + pad)
        dest = workdir / f"edge_{rank}_{side}_{int(pad)}.mp3"
        window = client.transcribe_sentences(_cut(audio, w0, w1 - w0, dest))
        found = locate_edge(words, window, t - w0, side) if window else None
        if found is not None:
            return w0 + found
    return None


def polish_one(clip: Clip, audio: Path, total: float, client, workdir: Path) -> Clip:
    """Confirm both edges by listening again around them; move them to the real words.
    A clip whose edges cannot be heard is kept but flagged as unverified."""
    words = normalize(clip.text)
    if len(words) < 2 * EDGE_WORDS:
        return clip
    try:
        start = _heard_edge(words[:EDGE_WORDS], "start", clip.start, audio, total,
                            client, workdir, clip.rank)
        end = _heard_edge(words[-EDGE_WORDS:], "end", clip.end, audio, total,
                          client, workdir, clip.rank)
    except QuotaError:
        return clip
    except Exception as e:  # noqa: BLE001 - polishing must never lose a clip
        print(f"polish clip {clip.rank} skipped: {type(e).__name__}", file=sys.stderr, flush=True)
        return clip
    new_start = clip.start if start is None else max(0.0, start - LEAD)
    new_end = clip.end if end is None else min(total, end + TAIL)
    if not MIN_LEN <= new_end - new_start <= MAX_LEN:
        print(f"polish clip {clip.rank}: result {new_start:.1f}-{new_end:.1f} out of range, "
              f"kept {clip.start:.1f}-{clip.end:.1f}", file=sys.stderr, flush=True)
        return replace(clip, shaky=True)
    print(f"polish clip {clip.rank}: start {clip.start:.1f}->{new_start:.1f} "
          f"({'heard' if start is not None else 'NOT heard'}), "
          f"end {clip.end:.1f}->{new_end:.1f} ({'heard' if end is not None else 'NOT heard'})",
          file=sys.stderr, flush=True)
    return replace(clip, start=new_start, end=new_end,
                   shaky=start is None or end is None)


def polish_edges(clips: list[Clip], audio: Path, total: float, client, workdir: Path,
                 workers: int = 3) -> list[Clip]:
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(polish_one, c, audio, total, client, workdir) for c in clips]
        return [f.result() for f in futures]

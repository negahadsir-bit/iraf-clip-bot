from models import Clip, Sentence

WARNING = " ⚠ پایان وسط جمله"


def snap_clips(clips: list[Clip], sentences: list[Sentence],
               tolerance: float = 8.0) -> list[Clip]:
    out = []
    for c in clips:
        starts = [s.start for s in sentences if abs(s.start - c.start) <= tolerance]
        start = min(starts, key=lambda v: (abs(v - c.start), v)) if starts else c.start
        ends = [s.end for s in sentences
                if s.end > start and abs(s.end - c.end) <= tolerance]
        if ends:
            end, reason = min(ends, key=lambda v: (abs(v - c.end), -v)), c.reason
        else:
            end, reason = c.end, c.reason + WARNING
        out.append(Clip(c.rank, start, end, reason))
    return sorted(out, key=lambda c: c.rank)

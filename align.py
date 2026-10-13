import re
from difflib import SequenceMatcher

from models import Sentence

K = 6  # words compared at each edge of a clip
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)


def normalize(text: str) -> list[str]:
    t = text.translate(_DIGITS).replace("ي", "ی").replace("ك", "ک").replace("‌", " ")
    return _PUNCT.sub(" ", t).split()


def _tokens(sentences: list[Sentence]) -> list[tuple[str, float, float]]:
    out = []
    for s in sentences:
        words = normalize(s.text)
        n = len(words)
        for m, w in enumerate(words):
            out.append((w, s.start + (s.end - s.start) * m / n,
                        s.start + (s.end - s.start) * (m + 1) / n))
    return out


def _best(edge: list[str], toks, expect: float, min_ratio: float):
    k = len(edge)
    best, best_score = None, -1.0
    for i in range(0, len(toks) - k + 1):
        r = SequenceMatcher(None, edge, [t[0] for t in toks[i:i + k]]).ratio()
        if r < min_ratio:
            continue
        score = r - abs(toks[i][1] - expect) / 1000.0  # ties go to the expected place
        if score > best_score:
            best, best_score = i, score
    return best


def locate(clip_text: str, window: list[Sentence], expect_start: float,
           min_ratio: float = 0.6) -> tuple[float, float] | None:
    """Find where clip_text sits in a freshly transcribed window; returns (start, end)
    in the window's own clock, or None if its beginning and end are not both found."""
    words = normalize(clip_text)
    toks = _tokens(window)
    if len(words) < 8 or len(toks) < 8:
        return None
    k = min(K, len(words) // 2)
    i = _best(words[:k], toks, expect_start, min_ratio)
    j = _best(words[-k:], toks, expect_start + len(words) / 2.6, min_ratio)
    if i is None or j is None or j + k - 1 <= i:
        return None
    return toks[i][1], toks[j + k - 1][2]

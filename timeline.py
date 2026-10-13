from models import Sentence, Word

_TERMINATORS = (".", "؟", "?", "!")


def fix_word_times(words: list[Word]) -> list[Word]:
    """Keep a start only if within -1s/+20s of the previous kept start;
    interpolate the rest linearly between the surrounding kept starts."""
    n = len(words)
    good: list[float | None] = [None] * n
    last = 0.0
    for i, w in enumerate(words):
        if last - 1.0 <= w.start <= last + 20.0:
            good[i] = w.start
            last = max(last, w.start)
    i = 0
    while i < n:
        if good[i] is not None:
            i += 1
            continue
        j = i
        while j < n and good[j] is None:
            j += 1
        a = good[i - 1] if i > 0 else 0.0
        b = good[j] if j < n else a + (j - i)
        for k in range(i, j):
            good[k] = a + (b - a) * (k - i + 1) / (j - i + 1)
        i = j
    return [Word(w.text, good[i], max(w.end, good[i])) for i, w in enumerate(words)]


def _word_end(words: list[Word], i: int) -> float:
    w = words[i]
    if w.end >= w.start and w.end - w.start < 4.0:
        return w.end
    nxt = words[i + 1].start if i + 1 < len(words) else w.start + 0.7
    return min(w.start + 0.7, nxt)


def words_to_sentences(words: list[Word]) -> list[Sentence]:
    sentences: list[Sentence] = []
    first = 0
    for i, w in enumerate(words):
        if w.text.endswith(_TERMINATORS) or i == len(words) - 1:
            text = " ".join(x.text for x in words[first:i + 1])
            sentences.append(Sentence(text, words[first].start, _word_end(words, i)))
            first = i + 1
    return sentences


def to_transcript(sentences: list[Sentence]) -> str:
    lines = []
    for s in sentences:
        sec = int(s.start)
        lines.append(f"{sec // 60}:{sec % 60:02d} {s.text}")
    return "\n".join(lines)


_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def parse_seconds(value) -> float:
    """Seconds from a number, "12.5", "01:23" or "1:02:03.5" (models mix formats)."""
    if isinstance(value, bool) or value is None:
        raise ValueError("no time")
    if isinstance(value, (int, float)):
        return float(value)
    parts = str(value).translate(_DIGITS).strip().replace(",", ".").split(":")
    total = 0.0
    for p in parts:
        total = total * 60 + float(p)
    return total

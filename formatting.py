from models import Clip, Sentence

LIMIT = 4096
MAX_REASON = 400
EDGE_WORDS = 7


def fmt_time(seconds: float) -> str:
    tenths = round(seconds * 10)
    minutes, rem = divmod(tenths, 600)
    return f"{minutes}:{rem / 10:04.1f}"


def _clip_words(clip: Clip, sentences: list[Sentence]) -> list[str]:
    inside = [s.text for s in sentences
              if s.start >= clip.start - 0.05 and s.end <= clip.end + 0.05]
    return " ".join(inside).split()


def _edges(words: list[str]) -> tuple[str, str]:
    if not words:
        return "—", "—"
    if len(words) <= EDGE_WORDS:
        full = " ".join(words)
        return full, full
    return " ".join(words[:EDGE_WORDS]) + "…", "…" + " ".join(words[-EDGE_WORDS:])


def _block(clip: Clip, sentences: list[Sentence]) -> str:
    start_text, end_text = _edges(_clip_words(clip, sentences))
    reason = clip.reason if len(clip.reason) <= MAX_REASON else clip.reason[:MAX_REASON] + "…"
    return (f"{clip.rank}) {fmt_time(clip.start)} – {fmt_time(clip.end)} "
            f"({round(clip.end - clip.start)}ث)\n"
            f"   شروع: «{start_text}»\n"
            f"   پایان: «{end_text}»\n"
            f"   چرا: {reason}")


def format_messages(clips: list[Clip], sentences: list[Sentence],
                    episode_seconds: float) -> list[str]:
    total = int(episode_seconds)
    header = f"✅ {len(clips)} پیشنهاد برش (مدت قسمت {total // 60}:{total % 60:02d})"
    messages: list[str] = []
    current = header
    for clip in clips:
        block = _block(clip, sentences)
        if len(current) + 2 + len(block) <= LIMIT:
            current += "\n\n" + block
        else:
            messages.append(current)
            current = block
    messages.append(current)
    return messages


def format_clip(clip: Clip, sentences: list[Sentence]) -> str:
    dialogue = clip.text or " ".join(
        s.text for s in sentences
        if s.start >= clip.start - 0.05 and s.end <= clip.end + 0.05) or "—"
    reason = clip.reason if len(clip.reason) <= MAX_REASON else clip.reason[:MAX_REASON] + "…"
    title = f"🔥 برش {clip.rank} · اولویت پیشنهادی" if clip.top else f"🎬 برش {clip.rank}"
    head = (f"{title}\n"
            f"{fmt_time(clip.start)} – {fmt_time(clip.end)} ({round(clip.end - clip.start)}ث)\n\n")
    tail = f"\n\nچرا: {reason}"
    room = LIMIT - len(head) - len(tail) - 2
    if len(dialogue) > room:
        dialogue = dialogue[:room - 1] + "…"
    return f"{head}«{dialogue}»{tail}"

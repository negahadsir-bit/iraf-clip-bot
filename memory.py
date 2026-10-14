import json
import time
from pathlib import Path

from categories import CATS

PER_CAT = 5
DISLIKED = 3
REASONS = 6
LINE_CHARS = 160   # an example needs its gist, not the whole clip
MAX_NOTE = 3000    # a longer prompt note drowns the rules and the transcript
CLIP_CHARS = 240


def _append(path: Path, entry: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def save_interview(path: Path, cats, clips) -> None:
    """Remember what was chosen for an interview the user labelled (append-only, one line each)."""
    _append(path, {"ts": int(time.time()), "cats": [CATS[i] for i in cats],
                   "clips": [{"text": c.text[:CLIP_CHARS], "reason": c.reason} for c in clips]})


def save_feedback(path: Path, good: bool, cats, text: str) -> None:
    """One 👍/👎 verdict on a single clip, filed under the interview's categories."""
    _append(path, {"ts": int(time.time()), "good": bool(good),
                   "cats": [CATS[i] for i in cats if 0 <= i < len(CATS)], "text": text[:CLIP_CHARS]})


def save_viral(path: Path, viral: bool, cats, text: str) -> None:
    """The user's own experience-based call: did this clip have viral potential or not."""
    _append(path, {"ts": int(time.time()), "viral": bool(viral),
                   "cats": [CATS[i] for i in cats if 0 <= i < len(CATS)], "text": text[:CLIP_CHARS]})


def save_reason(path: Path, cats, text: str, reason: str) -> None:
    """Why the user thought a clip was weak, in their own words."""
    _append(path, {"ts": int(time.time()), "reason": reason.strip()[:400],
                   "cats": [CATS[i] for i in cats if 0 <= i < len(CATS)], "text": text[:CLIP_CHARS]})


def _reasons(feedback: list[dict], cat: str) -> list[str]:
    return [f"{e['reason']} (نمونه: «{str(e.get('text', ''))[:80]}»)" for e in reversed(feedback)
            if e.get("reason") and cat in e["cats"]]


def _read(path: Path | None) -> list[dict]:
    if path is None:
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if isinstance(e, dict) and isinstance(e.get("cats"), list):
            out.append(e)
    return out


def _short(t: str) -> str:
    t = " ".join(str(t).split())
    return t if len(t) <= LINE_CHARS else t[:LINE_CHARS - 1] + "…"


def _verdicts(feedback: list[dict], cat: str, good: bool) -> list[str]:
    return [_short(e["text"]) for e in reversed(feedback)
            if e.get("good") is good and cat in e["cats"] and e.get("text")]


def _virality(feedback: list[dict], cat: str, viral: bool) -> list[str]:
    return [_short(e["text"]) for e in reversed(feedback)
            if e.get("viral") is viral and cat in e["cats"] and e.get("text")]


def _picks(interviews: list[dict], cat: str, limit: int) -> list[str]:
    texts: list[str] = []
    for e in reversed(interviews):
        clips = e.get("clips")
        if cat in e["cats"] and isinstance(clips, list):
            texts += [_short(c.get("text", "")) for c in clips[:2] if isinstance(c, dict) and c.get("text")]
        if len(texts) >= limit:
            break
    return texts[:limit]


def examples_note(path: Path | None, cats, feedback_path: Path | None = None) -> str:
    """Prompt text built from the user's own verdicts (and earlier picks) for the chosen categories."""
    if not cats:
        return ""
    interviews, feedback = _read(path), _read(feedback_path)
    blocks, names = [], []
    for i in sorted(set(cats)):
        if not 0 <= i < len(CATS):
            continue
        viral = _virality(feedback, CATS[i], True)[:PER_CAT]
        flat = _virality(feedback, CATS[i], False)[:DISLIKED]
        liked = _verdicts(feedback, CATS[i], True)[:PER_CAT]
        disliked = _verdicts(feedback, CATS[i], False)[:DISLIKED]
        known = len(viral) + len(liked)
        picks = _picks(interviews, CATS[i], PER_CAT - known) if known < PER_CAT else []
        parts = []
        why = _reasons(feedback, CATS[i])[:REASONS]
        if why:
            parts.append("دلایلی که کاربر برای ضعیف بودن برش‌ها گفته (این اشتباه‌ها را نکن):\n"
                         + "\n".join(f"- {t}" for t in why))
        if viral:
            parts.append("برش‌هایی که به تجربه‌ی کاربر وایرال شدند (علامت top را بیشتر از روی این‌ها بده):\n"
                         + "\n".join(f"- «{t}»" for t in viral))
        if liked:
            parts.append("برش‌هایی که کاربر پسندید (مثل این‌ها بساز):\n" + "\n".join(f"- «{t}»" for t in liked))
        if flat:
            parts.append("برش‌هایی که به تجربه‌ی کاربر وایرال نشدند (اولویت پایین‌تر بده، اما حذفشان نکن؛ ممکن است جای دیگری به کار بیایند):\n" + "\n".join(f"- «{t}»" for t in flat))
        if disliked:
            parts.append("برش‌هایی که کاربر نپسندید (اولویت پایین‌تر بده، اما اگر مناسب بودند حذفشان نکن):\n" + "\n".join(f"- «{t}»" for t in disliked))
        if picks:
            parts.append("پیشنهادهای قبلی همین دسته:\n" + "\n".join(f"- «{t}»" for t in picks))
        if parts:
            blocks.append(parts)
            names.append(CATS[i])
    if not blocks:
        return ""
    head = "نمونه‌هایی از مصاحبه‌های قبلیِ همین دسته‌ها برای درک سلیقه‌ی کاربر (کپی‌شان نکن):\n"
    share = (MAX_NOTE - len(head)) // len(blocks)  # every category gets an equal slice
    out = []
    for name, parts in zip(names, blocks):
        title = f"دسته‌ی «{name}»:\n"
        while len(parts) > 1 and len(title) + len("\n".join(parts)) > share:
            parts = parts[:-1]  # least useful part goes first (parts are in priority order)
        out.append((title + "\n".join(parts))[:share])
    return head + "\n".join(out)

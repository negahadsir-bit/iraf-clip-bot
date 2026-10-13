import json
import time
from pathlib import Path

from categories import CATS

PER_CAT = 5
CLIP_CHARS = 240


def save_interview(path: Path, cats, clips) -> None:
    """Remember what was chosen for an interview the user labelled (append-only, one line each)."""
    entry = {"ts": int(time.time()), "cats": [CATS[i] for i in cats],
             "clips": [{"text": c.text[:CLIP_CHARS], "reason": c.reason} for c in clips]}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _entries(path: Path) -> list[dict]:
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
        if isinstance(e, dict) and isinstance(e.get("cats"), list) and isinstance(e.get("clips"), list):
            out.append(e)
    return out


def examples_note(path: Path | None, cats) -> str:
    """Prompt text with clips picked in earlier interviews the user filed under the same categories."""
    if path is None or not cats:
        return ""
    entries = list(reversed(_entries(path)))  # newest first
    blocks = []
    for i in sorted(set(cats)):
        if not 0 <= i < len(CATS):
            continue
        texts = []
        for e in entries:
            if CATS[i] in e["cats"]:
                texts += [str(c.get("text", "")) for c in e["clips"][:2] if isinstance(c, dict) and c.get("text")]
            if len(texts) >= PER_CAT:
                break
        if texts:
            blocks.append(f"دسته‌ی «{CATS[i]}»:\n" + "\n".join(f"- «{t}»" for t in texts[:PER_CAT]))
    if not blocks:
        return ""
    return ("نمونه‌هایی از برش‌هایی که در مصاحبه‌های قبلیِ همین دسته‌ها انتخاب شده‌اند "
            "(فقط برای درک سلیقه؛ کپی‌شان نکن):\n" + "\n".join(blocks))

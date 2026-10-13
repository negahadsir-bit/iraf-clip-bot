import re
from pathlib import Path

from categories import CATS
from memory import CLIP_CHARS, save_feedback

_DATA = re.compile(r"f([+-])(\d{1,2})")
_DIALOGUE = re.compile(r"«(.*)»", re.S)
DONE = "noop"


def cats_mask(cats) -> int:
    return sum(1 << i for i in set(cats) if 0 <= i < len(CATS))


def clip_keyboard(cats) -> dict:
    """👍/👎 under a clip; the interview's categories ride along in the button data (stateless)."""
    m = cats_mask(cats)
    return {"inline_keyboard": [[{"text": "👍 خوب بود", "callback_data": f"f+{m}"},
                                 {"text": "👎 ضعیف بود", "callback_data": f"f-{m}"}]]}


def handle_feedback(cb: dict, cfg, tg, path: Path | None) -> bool:
    """Record a 👍/👎 press. Returns True when the callback was a feedback press."""
    m = _DATA.fullmatch(cb.get("data", ""))
    if not m:
        return False
    msg = cb.get("message") or {}
    chat_id = msg.get("chat", {}).get("id")
    if chat_id not in cfg.allowed_chat_ids:
        return True
    good = m.group(1) == "+"
    cats = [i for i in range(len(CATS)) if int(m.group(2)) >> i & 1]
    text = msg.get("text", "")
    d = _DIALOGUE.search(text)
    dialogue = (d.group(1) if d else text).strip()[:CLIP_CHARS]
    if path is not None and dialogue:
        try:
            save_feedback(path, good, cats, dialogue)
        except OSError:
            pass
    try:
        tg.edit_markup(chat_id, msg["message_id"],
                       {"inline_keyboard": [[{"text": "✅ ثبت شد " + ("👍" if good else "👎"),
                                              "callback_data": DONE}]]})
    except Exception:  # noqa: BLE001
        pass
    try:
        tg.answer_callback(cb["id"], "ثبت شد")
    except Exception:  # noqa: BLE001
        pass
    return True

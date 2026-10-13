import re
from pathlib import Path

from categories import CATS
from memory import CLIP_CHARS, save_feedback, save_viral

_DATA = re.compile(r"f([+-])(\d{1,2})")
_VIRAL = re.compile(r"v([+-])(\d{1,2})([yns])")
_DIALOGUE = re.compile(r"«(.*)»", re.S)
DONE = "noop"


def cats_mask(cats) -> int:
    return sum(1 << i for i in set(cats) if 0 <= i < len(CATS))


def clip_keyboard(cats) -> dict:
    """👍/👎 under a clip; the interview's categories ride along in the button data (stateless)."""
    m = cats_mask(cats)
    return {"inline_keyboard": [[{"text": "👍 خوب بود", "callback_data": f"f+{m}"},
                                 {"text": "👎 ضعیف بود", "callback_data": f"f-{m}"}]]}


def viral_keyboard(good: bool, mask: int) -> dict:
    """Second step, shown after 👍/👎: does this clip have viral potential, by the user's experience?"""
    g = "+" if good else "-"
    return {"inline_keyboard": [[{"text": "🚀 وایرال می‌شد", "callback_data": f"v{g}{mask}y"},
                                 {"text": "🧊 وایرال نمی‌شد", "callback_data": f"v{g}{mask}n"}],
                                [{"text": "⏭ رد کردن", "callback_data": f"v{g}{mask}s"}]]}


def _dialogue(msg: dict) -> str:
    text = msg.get("text", "")
    d = _DIALOGUE.search(text)
    return (d.group(1) if d else text).strip()[:CLIP_CHARS]


def _edit(tg, chat_id, msg, markup) -> None:
    try:
        tg.edit_markup(chat_id, msg["message_id"], markup)
    except Exception:  # noqa: BLE001
        pass


def _answer(tg, cb, text="ثبت شد") -> None:
    try:
        tg.answer_callback(cb["id"], text)
    except Exception:  # noqa: BLE001
        pass


def handle_feedback(cb: dict, cfg, tg, path: Path | None) -> bool:
    """Record a 👍/👎 press, then the viral question that follows it.
    Returns True when the callback belonged to this feedback flow."""
    data = cb.get("data", "")
    v = _VIRAL.fullmatch(data)
    if v:
        return _handle_viral(cb, cfg, tg, path, v)
    m = _DATA.fullmatch(data)
    if not m:
        return False
    msg = cb.get("message") or {}
    chat_id = msg.get("chat", {}).get("id")
    if chat_id not in cfg.allowed_chat_ids:
        return True
    good = m.group(1) == "+"
    mask = int(m.group(2))
    cats = [i for i in range(len(CATS)) if mask >> i & 1]
    dialogue = _dialogue(msg)
    if path is not None and dialogue:
        try:
            save_feedback(path, good, cats, dialogue)
        except OSError:
            pass
    if good:
        _edit(tg, chat_id, msg, viral_keyboard(good, mask))
        _answer(tg, cb, "ثبت شد؛ حالا وایرال بودنش؟")
    else:  # a weak clip is obviously not viral: no second question
        _edit(tg, chat_id, msg, {"inline_keyboard": [[{"text": "✅ ثبت شد 👎", "callback_data": DONE}]]})
        _answer(tg, cb)
    return True


def _handle_viral(cb: dict, cfg, tg, path: Path | None, v) -> bool:
    msg = cb.get("message") or {}
    chat_id = msg.get("chat", {}).get("id")
    if chat_id not in cfg.allowed_chat_ids:
        return True
    good, mask, answer = v.group(1) == "+", int(v.group(2)), v.group(3)
    cats = [i for i in range(len(CATS)) if mask >> i & 1]
    dialogue = _dialogue(msg)
    if answer != "s" and path is not None and dialogue:
        try:
            save_viral(path, answer == "y", cats, dialogue)
        except OSError:
            pass
    mark = {"y": " 🚀", "n": " 🧊", "s": ""}[answer]
    _edit(tg, chat_id, msg, {"inline_keyboard": [[{"text": "✅ ثبت شد " + ("👍" if good else "👎") + mark,
                                                  "callback_data": DONE}]]})
    _answer(tg, cb)
    return True

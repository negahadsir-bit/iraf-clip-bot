from categories import CATS

OK = "ok"
MARK = "✅ "


def keyboard(selected) -> dict:
    sel = set(selected)
    btn = [{"text": (MARK if i in sel else "") + name, "callback_data": f"t{i}"}
           for i, name in enumerate(CATS)]
    return {"inline_keyboard": [btn[:2], btn[2:], [{"text": "✔️ تأیید دسته‌بندی", "callback_data": OK}]]}


def selected_from(markup: dict | None) -> set[int]:
    """The chat message itself is the state: read which buttons are ticked."""
    out = set()
    for row in (markup or {}).get("inline_keyboard", []):
        for b in row:
            data = b.get("callback_data", "")
            if data.startswith("t") and b.get("text", "").startswith(MARK.strip()):
                out.add(int(data[1:]))
    return out


def handle_callback(cb: dict, cfg, tg) -> None:
    msg = cb.get("message") or {}
    chat_id = msg.get("chat", {}).get("id")
    if chat_id not in cfg.allowed_chat_ids:
        return
    sel = selected_from(msg.get("reply_markup"))
    data = cb.get("data", "")
    note = ""
    try:
        if data.startswith("t") and data[1:].isdigit() and int(data[1:]) < len(CATS):
            i = int(data[1:])
            sel ^= {i}
            tg.edit_markup(chat_id, msg["message_id"], keyboard(sel))
        elif data == OK:
            label = "، ".join(CATS[i] for i in sorted(sel)) or "بدون دسته"
            tg.edit_message(chat_id, msg["message_id"],
                            f"{msg.get('text', '')}\n\n🏷 دسته: {label}",
                            reply_markup={"inline_keyboard": []})
            note = "ثبت شد"
    except Exception:  # noqa: BLE001 - a stale button must never crash the bot
        pass
    try:
        tg.answer_callback(cb["id"], note)
    except Exception:  # noqa: BLE001 - too-old queries are refused by Telegram
        pass

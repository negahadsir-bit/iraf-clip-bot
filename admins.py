"""Admins added from inside the bot. They live in memory/admins.json (committed by the workflow
like the rest of memory/) and are merged into cfg.allowed_chat_ids, so every check that already
uses that set lets them in. Every admin can use the whole bot and add or remove other admins;
the ids in the ALLOWED_CHAT_IDS secret are the permanent «main» admins."""
import json
import re
from pathlib import Path

ADMINS = Path(__file__).parent / "memory" / "admins.json"

HELP = ("👥 مدیریت مدیران\n"
        "• /admins یا «مدیران» → فهرست مدیران\n"
        "• /addadmin 123456789 یا «افزودن مدیر 123456789» → اضافه کردن مدیر\n"
        "• /deladmin 123456789 یا «حذف مدیر 123456789» → حذف مدیر\n"
        "شناسهٔ عددی را خود شخص با فرستادن یک پیام به ربات می‌گیرد.\n"
        "هر مدیر همهٔ امکانات ربات را دارد و می‌تواند مدیر اضافه یا حذف کند.")

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def load(path: Path = ADMINS) -> list:
    try:
        return [int(x) for x in json.loads(path.read_text(encoding="utf-8"))]
    except Exception:
        return []


def _save(ids: list, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(set(ids))), encoding="utf-8")


def merge(cfg, path: Path = ADMINS) -> None:
    cfg.allowed_chat_ids.update(load(path))


def handle(msg: dict, cfg, tg, main_ids, path: Path = ADMINS) -> bool:
    """Admin commands from an admin's message; True when the message was one of them."""
    t = (msg.get("text") or "").strip().replace("‌", " ")
    if not t:
        return False
    chat = msg["chat"]["id"]
    low = t.lower()
    if low.startswith("/admins") or t in ("مدیران", "لیست مدیران", "فهرست مدیران"):
        extra = [x for x in load(path) if x not in main_ids]
        lines = [f"• {x} (اصلی)" for x in sorted(main_ids)] + [f"• {x}" for x in extra]
        tg.send_message(chat, "👥 مدیران ربات:\n" + "\n".join(lines) + "\n\n" + HELP)
        return True
    add = low.startswith("/addadmin") or t.startswith("افزودن مدیر") or t.startswith("اضافه کردن مدیر")
    rem = low.startswith("/deladmin") or low.startswith("/removeadmin") or t.startswith("حذف مدیر")
    if not (add or rem):
        return False
    m = re.search(r"-?\d{3,20}", t.translate(_DIGITS))
    if not m:
        tg.send_message(chat, "شناسهٔ عددی را بعد از دستور بنویس؛ مثلاً:\n/addadmin 123456789")
        return True
    who = int(m.group(0))
    saved = load(path)
    if add:
        if who in cfg.allowed_chat_ids:
            tg.send_message(chat, f"{who} از قبل مدیر است.")
            return True
        _save(saved + [who], path)
        cfg.allowed_chat_ids.add(who)
        tg.send_message(chat, f"✅ {who} مدیر شد و از حالا به همهٔ امکانات ربات دسترسی دارد.")
        try:
            tg.send_message(who, "👋 شما مدیر ربات برش کلیپ شدید.\n" + HELP)
        except Exception as e:  # they may not have started the bot yet
            print(f"welcome to new admin failed: {e}")
        return True
    if who in main_ids:
        tg.send_message(chat, f"{who} مدیر اصلی است و از داخل ربات حذف نمی‌شود.")
    elif who not in saved:
        tg.send_message(chat, f"{who} در فهرست مدیران نیست.")
    else:
        _save([x for x in saved if x != who], path)
        cfg.allowed_chat_ids.discard(who)
        tg.send_message(chat, f"🗑 {who} از مدیران حذف شد.")
    return True

import os
import sys
import tempfile
import time
from pathlib import Path

from buttons import ASK, handle_callback, keyboard
from config import ConfigError, load_config
from media import InputError, resolve_input
from pipeline import Deps, process
from telegram_api import Telegram, TelegramError

BUDGET_SECONDS = 5 * 60


def handle_update(update: dict, cfg, tg, process_fn, commit=None) -> int:
    """Handle one update; returns next offset. A file/link is first answered with the
    category question (nothing slow happens yet). Pressing «شروع» runs the work; the
    offset is committed right before that, so a crashed run never repeats the same file."""
    nxt = update["update_id"] + 1
    if update.get("callback_query"):
        handle_callback(update["callback_query"], cfg, tg, process_fn,
                        commit=(lambda: commit(nxt)) if commit else None)
        return nxt
    msg = update.get("message")
    if not msg or msg.get("chat", {}).get("id") not in cfg.allowed_chat_ids:
        return nxt
    chat_id = msg["chat"]["id"]
    try:
        resolve_input(msg)
    except InputError as e:
        tg.send_message(chat_id, str(e))
        return nxt
    tg.send_message(chat_id, ASK, reply_markup=keyboard(()), reply_to=msg.get("message_id"))
    return nxt


def main() -> int:
    try:
        cfg = load_config(os.environ)
    except ConfigError as e:
        print(str(e), file=sys.stderr)
        return 1
    from select_clips import make_select_client
    from transcribe import GeminiClient
    tg = Telegram(cfg.bot_token)
    rules = (Path(__file__).parent / "rules.md").read_text(encoding="utf-8")
    t_client, s_client = GeminiClient(cfg.gemini_key), make_select_client(os.environ, cfg.gemini_key)
    offset = None
    deadline = time.time() + BUDGET_SECONDS
    while time.time() < deadline:
        try:
            updates = tg.get_updates(offset, timeout=25)
        except TelegramError as e:
            print(f"telegram error: {e}", file=sys.stderr)
            time.sleep(5)
            continue
        for u in updates:
            with tempfile.TemporaryDirectory() as d:
                deps = Deps(tg, t_client, s_client, Path(d), rules)

                def commit(o):
                    nonlocal offset
                    offset = o
                    try:
                        tg.get_updates(o, timeout=0)  # acknowledge
                    except TelegramError:
                        pass

                offset = handle_update(u, cfg, tg, lambda m, cats: process(m, deps, cats), commit=commit)
    return 0


if __name__ == "__main__":
    sys.exit(main())

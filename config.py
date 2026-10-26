from dataclasses import dataclass
from typing import Mapping


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    bot_token: str
    gemini_key: str
    allowed_chat_ids: set  # the ALLOWED_CHAT_IDS secret plus admins added from inside the bot (admins.py)
    main_ids: frozenset = frozenset()


def load_config(env: Mapping[str, str]) -> Config:
    for name in ("BOT_TOKEN", "GEMINI_API_KEY", "ALLOWED_CHAT_IDS"):
        if not env.get(name):
            raise ConfigError(f"متغیر {name} تنظیم نشده است")
    ids = frozenset(int(p) for p in env["ALLOWED_CHAT_IDS"].split(",") if p.strip())
    return Config(env["BOT_TOKEN"], env["GEMINI_API_KEY"], set(ids), ids)

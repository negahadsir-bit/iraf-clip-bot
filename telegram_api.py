import json
import urllib.request
from pathlib import Path

API = "https://api.telegram.org"


class TelegramError(Exception):
    pass


class Telegram:
    def __init__(self, token: str):
        self._token = token

    def _call(self, method: str, payload: dict, timeout: int = 60) -> dict:
        req = urllib.request.Request(
            f"{API}/bot{self._token}/{method}",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.load(r)
        except Exception as exc:  # never leak the token in the message
            raise TelegramError(f"{method} failed: {type(exc).__name__}") from None
        if not data.get("ok"):
            raise TelegramError(f"{method} failed: {data.get('description', 'unknown')}")
        return data["result"]

    def get_updates(self, offset: int | None, timeout: int = 25) -> list[dict]:
        payload = {"timeout": timeout, "allowed_updates": ["message"]}
        if offset is not None:
            payload["offset"] = offset
        return self._call("getUpdates", payload, timeout=timeout + 15)

    def send_message(self, chat_id: int, text: str) -> int:
        return self._call("sendMessage", {"chat_id": chat_id, "text": text})["message_id"]

    def edit_message(self, chat_id: int, message_id: int, text: str) -> None:
        self._call("editMessageText",
                   {"chat_id": chat_id, "message_id": message_id, "text": text})

    def get_file_path(self, file_id: str) -> str:
        return self._call("getFile", {"file_id": file_id})["file_path"]

    def download(self, file_path: str, dest: Path) -> None:
        try:
            with urllib.request.urlopen(f"{API}/file/bot{self._token}/{file_path}",
                                        timeout=120) as r:
                Path(dest).write_bytes(r.read())
        except Exception as exc:
            raise TelegramError(f"download failed: {type(exc).__name__}") from None

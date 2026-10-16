import json
import os
import shutil
import uuid
import urllib.request
from pathlib import Path

API = "https://api.telegram.org"
LOCAL_ROOT = Path("/var/lib/telegram-bot-api")


class TelegramError(Exception):
    pass


class Telegram:
    """Talks to the cloud Bot API (files ≤ 20 MB) or, when TELEGRAM_API_URL is set, to a local
    Bot API server run by the workflow (files up to 2 GB; getFile then returns a local path)."""

    def __init__(self, token: str, base: str | None = None, data_dir: str | None = None):
        self._token = token
        self._base = (base or os.environ.get("TELEGRAM_API_URL") or API).rstrip("/")
        self._data = data_dir or os.environ.get("TELEGRAM_DATA") or ""

    def _call(self, method: str, payload: dict, timeout: int = 60) -> dict:
        req = urllib.request.Request(
            f"{self._base}/bot{self._token}/{method}",
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
        payload = {"timeout": timeout, "allowed_updates": ["message", "callback_query", "channel_post", "edited_channel_post"]}
        if offset is not None:
            payload["offset"] = offset
        return self._call("getUpdates", payload, timeout=timeout + 15)

    def send_message(self, chat_id: int, text: str, reply_markup: dict | None = None,
                     reply_to: int | None = None, entities: list | None = None) -> int:
        payload = {"chat_id": chat_id, "text": text}
        if entities:
            payload["entities"] = entities
            payload["link_preview_options"] = {"is_disabled": True}
        if reply_to is not None:
            payload["reply_to_message_id"] = reply_to
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        return self._call("sendMessage", payload)["message_id"]

    def edit_message(self, chat_id: int, message_id: int, text: str,
                     reply_markup: dict | None = None, entities: list | None = None) -> None:
        payload = {"chat_id": chat_id, "message_id": message_id, "text": text}
        if entities:
            payload["entities"] = entities
            payload["link_preview_options"] = {"is_disabled": True}
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        self._call("editMessageText", payload)

    def edit_markup(self, chat_id: int, message_id: int, reply_markup: dict) -> None:
        self._call("editMessageReplyMarkup",
                   {"chat_id": chat_id, "message_id": message_id, "reply_markup": reply_markup})

    def answer_callback(self, callback_id: str, text: str = "") -> None:
        self._call("answerCallbackQuery", {"callback_query_id": callback_id, "text": text})

    def send_video(self, chat_id: int, path, caption: str = "", timeout: int = 300) -> None:
        """Upload a local video (multipart); 1080x1920 H.264 plays inline."""
        boundary = "----iraf" + uuid.uuid4().hex
        body = b""
        for name, val in (("chat_id", str(chat_id)), ("caption", caption), ("supports_streaming", "true"),
                          ("width", "1080"), ("height", "1920")):
            body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{val}\r\n").encode()
        body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"video\"; filename=\"clip.mp4\"\r\n"
                 "Content-Type: video/mp4\r\n\r\n").encode() + Path(path).read_bytes() + f"\r\n--{boundary}--\r\n".encode()
        req = urllib.request.Request(f"{self._base}/bot{self._token}/sendVideo", data=body,
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.load(r)
        except Exception as exc:  # never leak the token in the message
            raise TelegramError(f"sendVideo failed: {type(exc).__name__}") from None
        if not data.get("ok"):
            raise TelegramError(f"sendVideo failed: {data.get('description', 'unknown')}")

    def get_file_path(self, file_id: str) -> str:
        return self._call("getFile", {"file_id": file_id})["file_path"]

    def download(self, file_path: str, dest: Path) -> None:
        try:
            if file_path.startswith("/"):  # local server: the file already sits on this machine
                src = Path(self._data) / Path(file_path).relative_to(LOCAL_ROOT) if self._data else Path(file_path)
                shutil.copyfile(src, dest)
                return
            with urllib.request.urlopen(f"{self._base}/file/bot{self._token}/{file_path}",
                                        timeout=120) as r:
                Path(dest).write_bytes(r.read())
        except Exception as exc:
            raise TelegramError(f"download failed: {type(exc).__name__}") from None

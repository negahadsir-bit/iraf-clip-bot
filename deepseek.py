import json
import time
import urllib.error
import urllib.request

from retry import BusyError, QuotaError

URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"
ATTEMPTS = 5

_JSON_NOTE = (
    "\n\nخروجی را فقط به صورت یک شیء JSON برگردان با کلید clips که مقدارش همان "
    'آرایه‌ی بالا باشد، مثل {"clips": [...]}.')


class HttpFailure(Exception):
    def __init__(self, status: int, text: str = ""):
        super().__init__(f"{status} {text}")
        self.status = status


def _post(url: str, headers: dict, body: str, timeout: int) -> dict:
    req = urllib.request.Request(url, data=body.encode(), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise HttpFailure(e.code, e.reason) from None
    except Exception as e:  # noqa: BLE001 - never leak the key in messages
        raise HttpFailure(0, type(e).__name__) from None


class DeepSeekTextClient:
    """Text-only selection client with the same generate_json interface as Gemini."""

    def __init__(self, api_key: str, model: str = MODEL, post=_post, sleep=time.sleep):
        self._key, self._model, self._post, self._sleep = api_key, model, post, sleep

    def generate_json(self, prompt: str) -> list[dict]:
        body = json.dumps({
            "model": self._model,
            "messages": [{"role": "user", "content": prompt + _JSON_NOTE}],
            "response_format": {"type": "json_object"},
            "temperature": 0.3,
        })
        headers = {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"}
        last = None
        for attempt in range(ATTEMPTS):
            try:
                data = self._post(URL, headers, body, 180)
                break
            except HttpFailure as e:
                last = e
                if e.status == 402:
                    raise QuotaError(f"deepseek: {e}") from None
                if e.status in (400, 401, 403, 404, 422):
                    raise RuntimeError(f"deepseek: {e}") from None
                self._sleep(5 * (attempt + 1))
        else:
            raise BusyError(f"deepseek: {last}")
        parsed = json.loads(data["choices"][0]["message"]["content"])
        if isinstance(parsed, dict):
            parsed = parsed.get("clips", [])
        return parsed

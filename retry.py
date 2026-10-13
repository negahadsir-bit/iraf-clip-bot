import os
import re
import time

_BUSY_MARKERS = ("503", "UNAVAILABLE", "500 INTERNAL", "high demand", "overloaded",
                 "disconnected", "timed out", "Timeout", "ReadError", "ConnectError")


class BusyError(Exception):
    pass


class QuotaError(Exception):
    pass


def _is_rate_limited(exc: Exception) -> bool:
    text = str(exc)
    return "429" in text or "RESOURCE_EXHAUSTED" in text


def _retry_delay(exc: Exception) -> float:
    m = re.search(r"retryDelay['\"]?\s*:\s*['\"]?(\d+(?:\.\d+)?)s", str(exc))
    return min(float(m.group(1)) + 1, 65.0) if m else 30.0


def _is_missing(exc: Exception) -> bool:
    text = str(exc)
    return "404" in text or "NOT_FOUND" in text


def _is_busy(exc: Exception) -> bool:
    text = str(exc)
    return any(m in text for m in _BUSY_MARKERS)


def call_with_fallback(fn, models: list[str], attempts: int = 5, sleep=time.sleep):
    """Call fn(model); retry busy/rate-limit errors with waiting, then try the next model."""
    quota_hit, last = False, ""
    for model in models:
        for i in range(attempts):
            try:
                return fn(model)
            except Exception as e:  # noqa: BLE001
                if _is_missing(e):
                    break
                last = str(e)[:300]
                if _is_rate_limited(e):
                    quota_hit = True
                    if "PerDay" in str(e) or i == attempts - 1:
                        break
                    sleep(_retry_delay(e))
                    continue
                if not _is_busy(e):
                    raise
                quota_hit = False
                if i < attempts - 1:
                    sleep(min(5 * 2 ** i, 40))
    raise (QuotaError if quota_hit else BusyError)(last or "no model available")


def models_from_env() -> list[str]:
    raw = os.environ.get("GEMINI_MODELS", "gemini-3.8-flash,gemini-3.6-flash,gemini-3.5-flash-lite")
    return [m.strip() for m in raw.split(",") if m.strip()]

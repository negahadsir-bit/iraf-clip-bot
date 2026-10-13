import os
import time

_BUSY_MARKERS = ("503", "UNAVAILABLE", "500 INTERNAL", "high demand", "overloaded",
                 "disconnected", "timed out", "Timeout", "ReadError", "ConnectError")


class BusyError(Exception):
    pass


def _is_missing(exc: Exception) -> bool:
    text = str(exc)
    return "404" in text or "NOT_FOUND" in text


def _is_busy(exc: Exception) -> bool:
    text = str(exc)
    return any(m in text for m in _BUSY_MARKERS)


def call_with_fallback(fn, models: list[str], attempts: int = 5, sleep=time.sleep):
    """Call fn(model) retrying busy errors with backoff, then the next model."""
    for model in models:
        for i in range(attempts):
            try:
                return fn(model)
            except Exception as e:  # noqa: BLE001
                if _is_missing(e):
                    break
                if not _is_busy(e):
                    raise
                if i < attempts - 1:
                    sleep(min(5 * 2 ** i, 40))
    raise BusyError("all models busy")


def models_from_env() -> list[str]:
    raw = os.environ.get("GEMINI_MODELS", "gemini-3.8-flash,gemini-3.6-flash,gemini-3.5-flash-lite")
    return [m.strip() for m in raw.split(",") if m.strip()]

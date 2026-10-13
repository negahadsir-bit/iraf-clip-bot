import os
import time

_BUSY_MARKERS = ("503", "UNAVAILABLE", "500 INTERNAL", "high demand", "overloaded")


class BusyError(Exception):
    pass


def _is_busy(exc: Exception) -> bool:
    text = str(exc)
    return any(m in text for m in _BUSY_MARKERS)


def call_with_fallback(fn, models: list[str], attempts: int = 4, sleep=time.sleep):
    """Call fn(model) retrying busy errors with backoff, then the next model."""
    for model in models:
        for i in range(attempts):
            try:
                return fn(model)
            except Exception as e:  # noqa: BLE001
                if not _is_busy(e):
                    raise
                if i < attempts - 1:
                    sleep(min(5 * 2 ** i, 40))
    raise BusyError("all models busy")


def models_from_env() -> list[str]:
    primary = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
    fallback = os.environ.get("GEMINI_FALLBACK_MODEL", "gemini-2.5-flash")
    return [primary] if fallback == primary else [primary, fallback]

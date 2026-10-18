"""Deepgram Nova-3 (Persian): an independent second listening and acoustic word times.

Never required: every failure returns None so the bot carries on with Gemini alone."""
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

URL = "https://api.deepgram.com/v1/listen?model=nova-3&language=fa&smart_format=true&punctuate=true"
TIMEOUT = 120
TRIES = 2
NO_RETRY = (400, 401, 402, 403)  # bad key, no credit left, bad audio: trying again cannot help


def parse(body: dict):
    """{'text': transcript, 'words': [{'text', 'heard', 'start', 'end'}]}, or None when nothing was heard."""
    try:
        alt = body["results"]["channels"][0]["alternatives"][0]
    except (KeyError, IndexError, TypeError):
        return None
    words = []
    for w in alt.get("words") or []:
        try:
            t = str(w["word"]).strip()
            if t:
                words.append({"text": t, "heard": t, "start": float(w["start"]), "end": float(w["end"])})
        except (KeyError, TypeError, ValueError):
            continue
    text = str(alt.get("transcript") or "").strip()
    return {"text": text, "words": words} if text and words else None


class DeepgramClient:
    def __init__(self, api_key: str, opener=None, pause: float = 1.5):
        self._key = api_key
        self._open = opener or urllib.request.urlopen
        self._pause = pause

    def listen(self, audio: Path):
        """Transcript and per-word times of a short clip; None if Deepgram cannot be used right now."""
        try:
            data = Path(audio).read_bytes()
        except OSError:
            return None
        for attempt in range(TRIES):
            req = urllib.request.Request(URL, data=data, method="POST", headers={
                "Authorization": "Token " + self._key, "Content-Type": "audio/mpeg"})
            try:
                with self._open(req, timeout=TIMEOUT) as r:
                    return parse(json.load(r))
            except urllib.error.HTTPError as e:
                print(f"deepgram http {e.code}", file=sys.stderr, flush=True)
                if e.code in NO_RETRY:
                    return None
            except Exception as e:  # noqa: BLE001 - a second opinion is never worth failing the job
                print(f"deepgram failed: {type(e).__name__}", file=sys.stderr, flush=True)
            if attempt + 1 < TRIES:
                time.sleep(self._pause)
        return None

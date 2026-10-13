"""Manual probe: python3 scripts/probe_gemini.py audio.mp3  (needs GEMINI_API_KEY)."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from transcribe import GeminiClient  # noqa: E402

c = GeminiClient(os.environ["GEMINI_API_KEY"])
w = c.transcribe_words(Path(sys.argv[1]))
print("word times:", "yes" if w else "no", (w or [])[:5])
if not w:
    print(c.transcribe_sentences(Path(sys.argv[1]))[:5])

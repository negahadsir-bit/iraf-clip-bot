"""One-off: transcribe the «گپ» interviews listed in teaser/list.txt (name<TAB>url) with Gemini
and save each transcript to teaser/out/<name>.json (also printed to the log)."""
import json
import os
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from transcribe import GeminiClient, transcribe  # noqa: E402

HERE = Path(__file__).resolve().parent
out_dir = HERE / "out"
out_dir.mkdir(exist_ok=True)
client = GeminiClient(os.environ["GEMINI_API_KEY"])
for line in (HERE / "list.txt").read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    name, url = line.split("\t")
    dest_json = out_dir / f"{name}.json"
    if dest_json.exists():
        continue
    work = Path(tempfile.mkdtemp())
    audio = work / "a.mp3"
    with urllib.request.urlopen(url, timeout=300) as r:
        audio.write_bytes(r.read())
    skipped = []
    sents = transcribe(audio, client, workdir=work, workers=3,
                       progress=lambda d, t: print(f"{name}: chunk {d}/{t}", flush=True),
                       on_skip=lambda i, n: skipped.append(i))
    rows = [{"s": round(s.start, 2), "e": round(s.end, 2), "t": s.text} for s in sents]
    dest_json.write_text(json.dumps({"skipped": skipped, "rows": rows}, ensure_ascii=False, indent=0),
                         encoding="utf-8")
    print(f"{name}: {len(rows)} sentences, skipped chunks {skipped}", flush=True)

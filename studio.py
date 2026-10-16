"""Template studio: a cut clip sent with the caption «رندر» + its text is rendered in the
chosen template (گپ / یاران خراسانی) with the guest name and title, word-synced subtitles
and background music picked by the mood of the speech. All state lives in the bot's own
chat messages (button → reply with the name → reply with the title), nothing is stored."""
import json
import random
import re
import sys
from pathlib import Path

from media import InputError, InputRef, fetch_input, resolve_input, to_audio

TEMPLATES = {"gap": "گپ", "yaran": "یاران خراسانی"}
HEAD = "🎬"
_LINK = re.compile(r"https?://\S*drive\.google\.com\S*")
_TRIGGER = re.compile(r"(?is)^\s*(?:رندر|render)(?=\s|$)\s*(.*)$")
MOODS = ("غمگین", "احساسی", "حماسی", "آرام", "عاشقانه", "نوستالژیک", "انگیزشی", "امیدوار")
DEFAULT_MOOD = "آرام"
NEED_TEXT = "ویدیوی برش را روی پیام همان برش ریپلای کن (کپشن: رندر)، یا متن گفتار را بعد از «رندر» بنویس."
FAILED = "ساخت ویدیو ناموفق بود؛ دوباره امتحان کن."
ASK_TEMPLATE = "این برش در کدام قالب ساخته شود؟"
ASK_NAME = "✏️ نام مهمان را روی همین پیام ریپلای کن."
ASK_TITLE = "✏️ حالا عنوان مهمان را روی همین پیام ریپلای کن."


def render_text(message: dict) -> str | None:
    """The clip text when the caption starts with «رندر»; None for any other message."""
    m = _TRIGGER.match(message.get("caption") or message.get("text") or "")
    return _LINK.sub(" ", m.group(1)).strip() if m else None


def reply_dialogue(message: dict) -> str:
    """The clip's speech from the suggestion message this video replies to (the text inside «…»)."""
    m = re.search(r"«(.+)»", (message.get("reply_to_message") or {}).get("text") or "", re.S)
    return " ".join(m.group(1).split()) if m else ""


def keyboard() -> dict:
    return {"inline_keyboard": [[{"text": n, "callback_data": f"tp:{k}"} for k, n in TEMPLATES.items()]]}


def build(header: str, st: dict) -> str:
    lines = [f"{HEAD} {header}"]
    if st.get("template"):
        lines.append(f"قالب: {TEMPLATES[st['template']]}")
    if st.get("name"):
        lines.append(f"نام: {st['name']}")
    lines.append("متن: " + " ".join(st["text"].split()))
    lines.append(f"ref: {st['ref']}")
    return "\n".join(lines)


def parse(text: str) -> dict | None:
    """State of one of our messages, or None when it is not one."""
    if not text or not text.startswith(HEAD):
        return None
    st = {}
    for line in text.split("\n")[1:]:
        key, _, val = line.partition(": ")
        if key == "قالب":
            st["template"] = next((k for k, n in TEMPLATES.items() if n == val.strip()), None)
        elif key == "نام":
            st["name"] = val.strip()
        elif key == "متن":
            st["text"] = val.strip()
        elif key == "ref":
            st["ref"] = val.strip()
    return st if st.get("ref") and st.get("text") else None


def start(message: dict, text: str, tg) -> None:
    chat_id = message["chat"]["id"]
    text = text or reply_dialogue(message)
    if not text:
        tg.send_message(chat_id, NEED_TEXT)
        return
    try:
        ref = resolve_input(message)
    except InputError as e:
        tg.send_message(chat_id, str(e))
        return
    key = ref.ref if ref.kind == "telegram" else "drive:" + ref.ref
    tg.send_message(chat_id, build(ASK_TEMPLATE, {"text": text, "ref": key}),
                    reply_markup=keyboard(), reply_to=message.get("message_id"))


def handle_callback(cb: dict, cfg, tg) -> bool:
    """«tp:<template>» buttons; True when the callback was ours."""
    data = cb.get("data", "")
    if not data.startswith("tp:"):
        return False
    msg = cb.get("message") or {}
    chat_id = msg.get("chat", {}).get("id")
    key = data[3:]
    st = parse(msg.get("text"))
    if chat_id not in cfg.allowed_chat_ids or st is None or key not in TEMPLATES:
        return True
    st["template"] = key
    try:
        tg.edit_message(chat_id, msg["message_id"], build(ASK_NAME, st), reply_markup={"inline_keyboard": []})
        tg.answer_callback(cb["id"])
    except Exception:  # noqa: BLE001 - a stale button must never crash the bot
        pass
    return True


def handle_reply(message: dict, cfg, tg, make) -> bool:
    """A reply to one of our questions: first the name, then the title (which renders)."""
    prev = message.get("reply_to_message") or {}
    st = parse(prev.get("text"))
    answer = (message.get("text") or "").strip()
    if st is None or not st.get("template") or not answer:
        return False
    chat_id = message["chat"]["id"]
    if not st.get("name"):
        st["name"] = " ".join(answer.split())
        tg.send_message(chat_id, build(ASK_TITLE, st), reply_to=message.get("message_id"))
        return True
    st["title"] = " ".join(answer.split())
    make(chat_id, st)
    return True


def choose_mood(client, text: str) -> str:
    prompt = ("حال‌وهوای این گفتار را برای انتخاب موسیقی زمینه تعیین کن. فقط یکی از این‌ها: "
              + "، ".join(MOODS) + f"\nگفتار:\n{text}\n"
              'فقط JSON برگردان: [{"mood": "..."}]')
    try:
        rows = client.generate_json(prompt)
        mood = str(rows[0].get("mood", "")).strip()
    except Exception as e:  # noqa: BLE001 - music is never worth failing the video
        print(f"mood fallback: {type(e).__name__}", file=sys.stderr, flush=True)
        return DEFAULT_MOOD
    return mood if mood in MOODS else DEFAULT_MOOD


def pick_music(mood: str, channel_rows: list, tg, workdir: Path, lufs_of, compose, presets, rng=random):
    """(file, lufs): a channel track tagged with the mood, else an original synthesized bed."""
    tagged = [r for r in channel_rows if r.get("file_id") and mood in r.get("tags", [])]
    if tagged:
        row = rng.choice(tagged)
        try:
            dest = Path(workdir) / "music_in.mp3"
            tg.download(tg.get_file_path(row["file_id"]), dest)
            return str(dest), lufs_of(str(dest))
        except Exception as e:  # noqa: BLE001
            print(f"channel track failed, composing: {type(e).__name__}", file=sys.stderr, flush=True)
    preset = presets.get(mood, "calm_ambient")
    row = compose(preset, str(workdir))
    path = str(Path(workdir) / row["file"])
    return path, lufs_of(path)


def make_video(chat_id: int, st: dict, tg, align_client, select_client, workdir: Path, music_catalog: Path) -> None:
    """Fetch the clip, time its words, pick music, render and send."""
    import gap_render
    import music_synth
    try:
        tg.send_message(chat_id, f"⏳ ساخت ویدیو در قالب «{TEMPLATES[st['template']]}» شروع شد (چند دقیقه)…")
        workdir = Path(workdir)
        kind, _, rid = st["ref"].partition(":") if st["ref"].startswith("drive:") else ("telegram", "", st["ref"])
        video = fetch_input(InputRef(kind, rid), tg, workdir)
        audio = to_audio(video, workdir / "studio_audio.mp3")
        rows = align_client.align_words(audio, st["text"])
        if not rows:
            raise ValueError("no word times")
        mood = choose_mood(select_client, st["text"])
        try:
            channel = json.loads(Path(music_catalog).read_text(encoding="utf-8")) if Path(music_catalog).exists() else []
        except (OSError, ValueError):
            channel = []
        music_file, music_lufs = pick_music(mood, channel, tg, workdir, gap_render.lufs_of, music_synth.compose,
                                            music_synth.MOOD_TO_PRESET)
        out = str(workdir / "studio_out.mp4")
        gap_render.main(str(video), st["text"], st["name"], st["title"], out, str(workdir / "render"), rows=rows,
                        music_file=music_file, music_lufs=music_lufs, template=st["template"])
        tg.send_video(chat_id, out, caption=f"{st['name']} — {st['title']}\n🎵 حال‌وهوا: {mood}")
    except InputError as e:
        tg.send_message(chat_id, str(e))
    except Exception as e:  # noqa: BLE001 - always answer the user
        print(f"studio failed: {type(e).__name__}: {str(e)[:300]}", file=sys.stderr, flush=True)
        tg.send_message(chat_id, FAILED)

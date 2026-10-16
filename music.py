import json
import re
from pathlib import Path

_TAG = re.compile(r"#([^\s#.,،؛:!?؟()«»\"']+)")


def hashtags(text: str) -> list[str]:
    """#hashtags of a post, underscores read as spaces (#آرام_بخش -> «آرام بخش»), no repeats."""
    seen, out = set(), []
    for t in _TAG.findall(text or ""):
        t = t.replace("_", " ").strip()
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def entry_from_post(post: dict) -> dict | None:
    """One catalog row for a channel post that carries a music file, else None."""
    f = post.get("audio")
    if not f:
        d = post.get("document") or {}
        if str(d.get("mime_type", "")).startswith("audio/"):
            f = d
    if not f:
        return None
    return {
        "id": f.get("file_unique_id") or f["file_id"],
        "file_id": f["file_id"],
        "chat_id": post.get("chat", {}).get("id"),
        "message_id": post.get("message_id"),
        "title": f.get("title") or f.get("file_name") or "",
        "performer": f.get("performer") or "",
        "duration": f.get("duration") or 0,
        "size": f.get("file_size") or 0,
        "tags": hashtags(post.get("caption") or post.get("text") or ""),
    }


def load(path: Path) -> list[dict]:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def add_post(path: Path, post: dict) -> bool:
    """Record a channel post's music in the catalog (new or edited post replaces its row)."""
    row = entry_from_post(post)
    if row is None:
        return False
    rows = [r for r in load(path) if r.get("id") != row["id"]]
    rows.append(row)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    return True


_PLAIN = {"message_id", "sender_chat", "chat", "date", "caption", "caption_entities", "entities",
          "author_signature", "forward_origin", "forward_from_chat", "forward_from_message_id",
          "forward_date", "forward_signature"}


def log_seen(path: Path, update: dict) -> None:
    """One line per channel update, whatever it carries: shows what Telegram really delivers."""
    post = update.get("channel_post") or update.get("edited_channel_post") or {}
    row = {"update_id": update.get("update_id"), "edited": "edited_channel_post" in update,
           "message_id": post.get("message_id"), "media_group_id": post.get("media_group_id"),
           "kinds": sorted(set(post) - _PLAIN)}
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

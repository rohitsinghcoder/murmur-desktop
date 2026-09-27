"""Dictation history as JSON lines in %USERPROFILE%\\.murmur, private to this Windows user.

Not in AppData: Microsoft Store Python silently redirects AppData writes into its sandbox, where
other apps (like Notepad for "Open history") can't find them.
"""
import json
import os
import time
from pathlib import Path

DIR = Path.home() / ".murmur"
FILE = DIR / "history.jsonl"
_OLD_FILE = Path(os.environ.get("APPDATA", Path.home())) / "Murmur" / "history.jsonl"


def _migrate():
    if _OLD_FILE.exists() and not FILE.exists():
        DIR.mkdir(parents=True, exist_ok=True)
        _OLD_FILE.replace(FILE)
        try:
            _OLD_FILE.parent.rmdir()
        except OSError:
            pass


def add(text: str, audio_ms: int, app: str | None):
    _migrate()
    DIR.mkdir(parents=True, exist_ok=True)
    entry = {"time": int(time.time() * 1000), "text": text, "audioMs": audio_ms, "app": app}
    with FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def delete(entry_time: int):
    """Removes the entry with this timestamp."""
    entries = [e for e in load() if e.get("time") != entry_time][::-1]
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries), encoding="utf-8")
    tmp.replace(FILE)


def stats(entries: list[dict]) -> dict:
    """Words dictated, speaking speed (words per minute) and the current daily streak."""
    words = sum(len(e.get("text", "").split()) for e in entries)
    minutes = sum(e.get("audioMs", 0) for e in entries) / 60000
    days = {time.localtime(e["time"] / 1000)[:3] for e in entries if "time" in e}
    streak = 0
    day = time.time()
    # A streak still counts if today's first dictation hasn't happened yet.
    if time.localtime(day)[:3] not in days:
        day -= 86400
    while time.localtime(day)[:3] in days:
        streak += 1
        day -= 86400
    return {"words": words, "wpm": round(words / minutes) if minutes > 0.1 else 0,
            "dictations": len(entries), "streak": streak}


def load() -> list[dict]:
    """Newest first."""
    _migrate()
    if not FILE.exists():
        return []
    out = []
    for line in FILE.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return out[::-1]

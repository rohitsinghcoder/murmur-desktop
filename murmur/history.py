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

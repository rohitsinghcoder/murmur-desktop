"""Dictation history as JSON lines in %APPDATA%\\Murmur, private to this Windows user."""
import json
import os
import time
from pathlib import Path

DIR = Path(os.environ.get("APPDATA", Path.home())) / "Murmur"
FILE = DIR / "history.jsonl"


def add(text: str, audio_ms: int, app: str | None):
    DIR.mkdir(parents=True, exist_ok=True)
    entry = {"time": int(time.time() * 1000), "text": text, "audioMs": audio_ms, "app": app}
    with FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def load() -> list[dict]:
    """Newest first."""
    if not FILE.exists():
        return []
    out = []
    for line in FILE.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return out[::-1]

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
# What inserter.foreground_app() calls Murmur's own window. Dictations into its try-it box are
# practice: they're not saved, and older ones already saved are left out of history and stats.
TRY_IT = "Murmur"
# An average typist, for "faster than typing" and the time saved.
TYPING_WPM = 40
# How long dictations are kept (the "keep_history" setting), in days; None is forever. "off"
# saves nothing new but leaves what's there until it's cleared.
KEEP = {"forever": None, "year": 365, "month": 30, "off": 0}
keep = "forever"  # set by the app from its settings


def _migrate():
    if _OLD_FILE.exists() and not FILE.exists():
        DIR.mkdir(parents=True, exist_ok=True)
        _OLD_FILE.replace(FILE)
        try:
            _OLD_FILE.parent.rmdir()
        except OSError:
            pass


def add(text: str, audio_ms: int, app: str | None):
    if app == TRY_IT or keep == "off":
        return
    _migrate()
    DIR.mkdir(parents=True, exist_ok=True)
    entry = {"time": int(time.time() * 1000), "text": text, "audioMs": audio_ms, "app": app}
    with FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    prune()


def _write(entries: list[dict]):
    """Replaces the history with these entries (newest first, as load() gives them)."""
    DIR.mkdir(parents=True, exist_ok=True)
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries[::-1]), encoding="utf-8")
    tmp.replace(FILE)


def delete(entry_time: int):
    """Removes the entry with this timestamp."""
    _write([e for e in load() if e.get("time") != entry_time])


def clear():
    FILE.unlink(missing_ok=True)


def prune():
    """Drops dictations older than the `keep` setting allows."""
    days = KEEP.get(keep)
    if not days or not FILE.exists():
        return
    cutoff = (time.time() - days * 86400) * 1000
    entries = load()
    kept = [e for e in entries if e.get("time", 0) >= cutoff]
    if len(kept) < len(entries):
        _write(kept)


def export(path: Path) -> int:
    """Writes every dictation, oldest first and grouped by day, to a Markdown (.md) or plain
    text file. Returns how many were written."""
    entries = load()[::-1]
    md = Path(path).suffix.lower() == ".md"
    lines = ["# Murmur history", ""] if md else []
    day = None
    for e in entries:
        t = time.localtime(e["time"] / 1000)
        if t[:3] != day:
            day = t[:3]
            heading = time.strftime("%A %d %B %Y", t)
            lines += [f"## {heading}", ""] if md else [heading, "=" * len(heading), ""]
        clock = time.strftime("%I:%M %p", t).lstrip("0")
        text = e.get("text", "").strip()
        if md:
            # Two trailing spaces keep a dictation's own line breaks in Markdown.
            lines += [f"**{clock}** " + text.replace("\n", "  \n"), ""]
        else:
            lines += [f"{clock}  " + text.replace("\n", "\n" + " " * (len(clock) + 2)), ""]
    Path(path).write_text("\n".join(lines), encoding="utf-8")
    return len(entries)


def stats(entries: list[dict]) -> dict:
    """Words dictated, speaking speed (words per minute), the current daily streak, and how
    much faster than typing that was."""
    entries = [e for e in entries if e.get("app") != TRY_IT]
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
    # Time saved: typing the same words at TYPING_WPM, less the time spent speaking them.
    spoke = minutes > 0.1
    typing = words / TYPING_WPM
    return {"words": words, "wpm": round(words / minutes) if spoke else 0,
            "dictations": len(entries), "streak": streak,
            "timesFaster": round(typing / minutes, 1) if spoke else 0,
            "minutesSaved": round(max(0.0, typing - minutes)) if spoke else 0}


def load() -> list[dict]:
    """Newest first."""
    _migrate()
    if not FILE.exists():
        return []
    out = []
    for line in FILE.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("app") != TRY_IT:
            out.append(entry)
    return out[::-1]

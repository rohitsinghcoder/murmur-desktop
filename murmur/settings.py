"""User settings in %USERPROFILE%\\.murmur\\settings.json."""
import json

from . import history
from .history import DIR

FILE = DIR / "settings.json"
DEFAULTS = {
    "hotkey": ["rctrl"],
    "theme": "system",  # system, light or dark
    # Text cleanup (murmur/pipeline.py).
    "remove_fillers": True,
    "digits": True,
    "voice_commands": True,  # "new line", "new paragraph" (murmur/commands.py)
    "microphone": "",  # a device name; "" is the Windows default (murmur/mics.py)
    "show_bar": True,  # the resting bar at the bottom of the screen
    "sounds": False,  # a soft sound when dictation starts and stops
    "keep_history": "forever",  # forever, year, month or off (history.KEEP)
    "dictionary": [],  # [heard, write] pairs (murmur/replace.py)
    "snippets": [],  # [trigger, text] pairs (murmur/replace.py)
}


def _pairs(v) -> bool:
    return isinstance(v, list) and len(v) <= 1000 and all(
        isinstance(p, list) and len(p) == 2 and all(isinstance(s, str) and 0 < len(s.strip()) <= 5000 for s in p)
        for p in v)


# Settings the window may change with Bridge.setOption, and what each must look like.
OPTIONS = {
    "remove_fillers": lambda v: isinstance(v, bool),
    "digits": lambda v: isinstance(v, bool),
    "voice_commands": lambda v: isinstance(v, bool),
    "microphone": lambda v: isinstance(v, str) and len(v) <= 300,
    "show_bar": lambda v: isinstance(v, bool),
    "sounds": lambda v: isinstance(v, bool),
    "keep_history": lambda v: isinstance(v, str) and v in history.KEEP,
    "dictionary": _pairs,
    "snippets": _pairs,
}


def valid(key: str, value) -> bool:
    return key in OPTIONS and OPTIONS[key](value)


def load() -> dict:
    try:
        data = json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {**DEFAULTS, **{k: v for k, v in data.items() if k in DEFAULTS and (k not in OPTIONS or valid(k, v))}}


def save(settings: dict):
    DIR.mkdir(parents=True, exist_ok=True)
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    tmp.replace(FILE)

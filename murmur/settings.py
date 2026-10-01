"""User settings in %USERPROFILE%\\.murmur\\settings.json."""
import copy
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
    "save_memory": False,  # unload the speech model after IDLE_UNLOAD_MIN without dictating
    "keep_history": "forever",  # forever, year, month or off (history.KEEP)
    "vocabulary": [],  # names and words to listen for (murmur/vocabulary.py)
    "dictionary": [],  # [heard, write] pairs (murmur/replace.py)
    "learn_fixes": True,  # learn words the user fixes after a dictation (murmur/fixes.py)
    # Fixes seen, by "heard -> write": real-word ones are learned the second time; undone ones never.
    "learned": {"seen": {}, "rejected": []},
    "snippets": [],  # [trigger, text] pairs (murmur/replace.py)
    "onboarded": False,  # the first-run checklist on Home was dismissed
}


def _pairs(v) -> bool:
    return isinstance(v, list) and len(v) <= 1000 and all(
        isinstance(p, list) and len(p) == 2 and all(isinstance(s, str) and 0 < len(s.strip()) <= 5000 for s in p)
        for p in v)


def _terms(v) -> bool:
    return isinstance(v, list) and len(v) <= 1000 and all(
        isinstance(s, str) and 0 < len(s.strip()) <= 100 for s in v)


# Settings the window may change with Bridge.setOption, and what each must look like.
OPTIONS = {
    "remove_fillers": lambda v: isinstance(v, bool),
    "digits": lambda v: isinstance(v, bool),
    "voice_commands": lambda v: isinstance(v, bool),
    "microphone": lambda v: isinstance(v, str) and len(v) <= 300,
    "show_bar": lambda v: isinstance(v, bool),
    "sounds": lambda v: isinstance(v, bool),
    "save_memory": lambda v: isinstance(v, bool),
    "keep_history": lambda v: isinstance(v, str) and v in history.KEEP,
    "vocabulary": _terms,
    "learn_fixes": lambda v: isinstance(v, bool),
    "dictionary": _pairs,
    "snippets": _pairs,
    "onboarded": lambda v: isinstance(v, bool),
}


def _learned(v) -> bool:
    return (isinstance(v, dict) and isinstance(v.get("seen"), dict) and isinstance(v.get("rejected"), list)
            and all(isinstance(k, str) and isinstance(n, int) for k, n in v["seen"].items())
            and all(isinstance(k, str) for k in v["rejected"]))


# Settings only Murmur itself changes, checked when read from the file.
INTERNAL = {"learned": _learned}


def valid(key: str, value) -> bool:
    return key in OPTIONS and OPTIONS[key](value)


def load() -> dict:
    try:
        data = json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    # Someone who dictated before the checklist existed doesn't need it.
    data.setdefault("onboarded", history.FILE.exists())
    checks = {**OPTIONS, **INTERNAL}
    return {**copy.deepcopy(DEFAULTS),
            **{k: v for k, v in data.items() if k in DEFAULTS and (k not in checks or checks[k](v))}}


def save(settings: dict):
    DIR.mkdir(parents=True, exist_ok=True)
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    tmp.replace(FILE)

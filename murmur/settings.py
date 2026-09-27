"""User settings in %USERPROFILE%\\.murmur\\settings.json."""
import json

from .history import DIR

FILE = DIR / "settings.json"
DEFAULTS = {
    "hotkey": ["rctrl"],
    "theme": "system",  # system, light or dark
    # Text cleanup (murmur/pipeline.py).
    "remove_fillers": True,
    "digits": True,
}
# Settings the window may change with Bridge.setOption, and what each must look like.
OPTIONS = {
    "remove_fillers": lambda v: isinstance(v, bool),
    "digits": lambda v: isinstance(v, bool),
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

"""User settings in %USERPROFILE%\\.murmur\\settings.json."""
import json

from .history import DIR

FILE = DIR / "settings.json"
DEFAULTS = {"hotkey": ["rctrl"]}


def load() -> dict:
    try:
        data = json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {**DEFAULTS, **{k: v for k, v in data.items() if k in DEFAULTS}}


def save(settings: dict):
    DIR.mkdir(parents=True, exist_ok=True)
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    tmp.replace(FILE)

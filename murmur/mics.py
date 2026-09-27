"""Microphones: the list in Settings, finding the chosen one, and a level meter for the mic
check on Home.

A microphone is remembered by name, because device numbers change when devices come and go.
Devices are listed from Windows' default audio system (MME, as dictation uses), which cuts
names at 31 characters; the full name is taken from another audio system that lists the same
device ("Microphone Array (Realtek(R) Au" -> "... Audio)").
"""
from typing import Callable

import sounddevice as sd

from . import dictation

# Windows' stand-ins for "whatever the default is", not real devices.
_ALIASES = ("Microsoft Sound Mapper", "Primary Sound Capture Driver")
_MME_NAME_LENGTH = 31


def inputs() -> list[dict]:
    """[{"index", "name"}] of the microphones, in Windows' order. "System default" isn't one of
    them: that's no device (None)."""
    devices = sd.query_devices()
    default = sd.default.device[0]
    api = devices[default]["hostapi"] if default is not None and default >= 0 else 0
    out, seen = [], set()
    for i, d in enumerate(devices):
        if d["hostapi"] != api or d["max_input_channels"] < 1 or d["name"].startswith(_ALIASES):
            continue
        name = _full_name(d["name"], devices)
        if name not in seen:
            seen.add(name)
            out.append({"index": i, "name": name})
    return out


def _full_name(name: str, devices) -> str:
    if len(name) < _MME_NAME_LENGTH:
        return name
    longer = [d["name"] for d in devices
              if d["max_input_channels"] > 0 and d["name"].startswith(name) and len(d["name"]) > len(name)]
    return min(longer, key=len) if longer else name


def default_name() -> str | None:
    try:
        d = sd.query_devices(kind="input")
    except sd.PortAudioError:
        return None
    return _full_name(d["name"], sd.query_devices())


def find(name: str) -> int | None:
    """The device number of the microphone called `name`; None (the system default) for "" or
    one that isn't connected."""
    if not name:
        return None
    return next((d["index"] for d in inputs() if d["name"] == name), None)


def refresh():
    """Looks for microphones plugged in or removed since Murmur started. PortAudio only lists
    devices when it starts, so this restarts it: only while no stream is open."""
    sd._terminate()
    sd._initialize()


class Monitor:
    """Reports the mic's loudness (0..1, as dictation.level) about 20 times a second, on the
    audio thread."""

    def __init__(self, on_level: Callable[[float], None]):
        self.on_level = on_level
        self.stream = None

    @property
    def running(self) -> bool:
        return self.stream is not None

    def start(self, device=None) -> bool:
        self.stop()
        try:
            self.stream = sd.InputStream(
                samplerate=dictation.SR, channels=1, dtype="float32", blocksize=dictation.BLOCK,
                device=device, callback=lambda indata, *_: self.on_level(dictation.level(indata[:, 0])),
            )
            self.stream.start()
        except Exception:
            self.stream = None
            return False
        return True

    def stop(self):
        if self.stream is not None:
            stream, self.stream = self.stream, None
            stream.stop()
            stream.close()

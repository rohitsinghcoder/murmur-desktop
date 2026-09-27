"""Regenerates assets/start.wav and assets/stop.wav: two soft notes, rising to start and falling
to stop, played when dictation starts and stops (if turned on in Settings).

    python scripts/make_sounds.py
"""
from pathlib import Path

import numpy as np
import soundfile as sf

SR = 44100
ASSETS = Path(__file__).resolve().parent.parent / "assets"


def note(freq: float, secs: float) -> np.ndarray:
    t = np.arange(int(SR * secs)) / SR
    # A quick attack and an exponential fade, with a touch of the octave for warmth.
    env = np.minimum(1, t / 0.006) * np.exp(-t / (secs / 4))
    return env * (np.sin(2 * np.pi * freq * t) + 0.18 * np.sin(4 * np.pi * freq * t))


def chime(freqs: list[float]) -> np.ndarray:
    out = np.zeros(int(SR * 0.2))
    for i, f in enumerate(freqs):
        start = int(SR * 0.055 * i)
        n = note(f, 0.2 - 0.055 * i)
        out[start:start + len(n)] += n
    return (0.22 * out / np.abs(out).max()).astype(np.float32)


sf.write(ASSETS / "start.wav", chime([659.3, 987.8]), SR, subtype="PCM_16")  # E5 then B5
sf.write(ASSETS / "stop.wav", chime([987.8, 659.3]), SR, subtype="PCM_16")
print(f"Wrote start.wav and stop.wav to {ASSETS}")

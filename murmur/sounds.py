"""Soft sounds when dictation starts and stops (Settings; off by default). UI thread only.

QSoundEffect plays without blocking. It's only loaded once the sounds are turned on, so Qt
Multimedia costs nothing for everyone else.
"""
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl

ASSETS = Path(__file__).resolve().parent.parent / "assets"
VOLUME = 0.6
# The mic keeps recording for dictation.TAIL_S after you stop; wait that out, so the stop sound
# isn't in the recording.
STOP_DELAY_MS = 250


class Sounds:
    def __init__(self):
        self.enabled = False
        self._effects = {}

    def set_enabled(self, on: bool):
        self.enabled = on
        if on and not self._effects:
            from PySide6.QtMultimedia import QSoundEffect
            for name in ("start", "stop"):
                effect = QSoundEffect()
                effect.setSource(QUrl.fromLocalFile(str(ASSETS / f"{name}.wav")))
                effect.setVolume(VOLUME)
                self._effects[name] = effect

    def start(self):
        if self.enabled:
            self._effects["start"].play()

    def stop(self):
        if self.enabled:
            QTimer.singleShot(STOP_DELAY_MS, self._effects["stop"].play)

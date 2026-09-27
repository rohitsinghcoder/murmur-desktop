"""Murmur for Windows: hold Right Ctrl, speak, release, and your words are typed into the focused app.

    python -m murmur
"""
import ctypes
import os
import sys
import threading
import time

import numpy as np
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import dictation, engine, history, hotkey, inserter
from .overlay import Overlay

HOTKEY_NAME = "Right Ctrl"


class App(QObject):
    # Signals carry events from background threads (hook, mic, decoder) to the UI thread.
    loaded = Signal(float)
    load_failed = Signal(str)
    start = Signal()
    finish = Signal()
    cancel = Signal()
    lock = Signal()
    partial = Signal(str)
    levels = Signal(list)
    done = Signal(str, int, int)
    error = Signal(str)

    def __init__(self, qt: QApplication):
        super().__init__()
        self.qt = qt
        self.overlay = Overlay()
        self.dictation: dictation.Dictation | None = None
        self.target_app: str | None = None

        self.tray = QSystemTrayIcon(mic_icon(QColor(150, 150, 160)))
        menu = QMenu()
        self.status = QAction("Loading the speech model…", enabled=False)
        menu.addAction(self.status)
        menu.addSeparator()
        menu.addAction("Open history", self.open_history)
        menu.addAction("Quit Murmur", qt.quit)
        self.menu = menu
        self.tray.setContextMenu(menu)
        self.tray.setToolTip("Murmur: loading…")
        self.tray.show()

        self.loaded.connect(self.on_loaded)
        self.load_failed.connect(self.on_load_failed)
        self.start.connect(self.on_start)
        self.finish.connect(self.on_finish)
        self.cancel.connect(self.on_cancel)
        self.lock.connect(self.overlay.locked)
        self.partial.connect(self.overlay.partial)
        self.levels.connect(self.overlay.set_levels)
        self.done.connect(self.on_done)
        self.error.connect(self.on_error)

        # Hook callbacks must return fast, so they only post to the UI thread.
        self.keys = hotkey.HoldToTalk(
            on_start=self.start.emit, on_finish=self.finish.emit,
            on_cancel=self.cancel.emit, on_lock=self.lock.emit,
        )
        self.keys.start()
        threading.Thread(target=self.load, daemon=True).start()

    def load(self):
        t0 = time.perf_counter()
        try:
            rec = engine.load()
            # Warm-up, so the first real dictation isn't slower.
            t = engine.Transcriber(rec)
            t.accept(np.zeros(engine.SAMPLE_RATE, dtype=np.float32))
            t.finish()
        except Exception as e:
            self.load_failed.emit(str(e))
            return
        self.dictation = dictation.Dictation(
            rec,
            on_partial=self.partial.emit,
            on_levels=self.levels.emit,
            on_done=self.done.emit,
            on_error=self.error.emit,
        )
        self.loaded.emit(time.perf_counter() - t0)

    # UI thread.

    def on_loaded(self, secs: float):
        self.status.setText(f"Ready: hold {HOTKEY_NAME} to dictate")
        self.tray.setIcon(mic_icon(QColor(124, 156, 255)))
        self.tray.setToolTip(f"Murmur: hold {HOTKEY_NAME} to dictate")
        self.overlay.show_message(f"Murmur is ready. Hold {HOTKEY_NAME} and speak", ms=3000)

    def on_load_failed(self, message: str):
        self.status.setText("Couldn't load the speech model")
        self.overlay.show_message(f"Couldn't load the speech model: {message}", error=True, ms=8000)

    def on_start(self):
        if self.dictation is None:
            self.overlay.show_message("Still loading the speech model…", ms=1500)
            return
        if self.dictation.listen():
            self.target_app = inserter.foreground_app()
            self.overlay.listening()

    def on_finish(self):
        if self.dictation and self.dictation.busy:
            self.dictation.finish()
            self.overlay.finishing()

    def on_cancel(self):
        if self.dictation:
            self.dictation.cancel()
        if self.overlay.mode in ("listening", "finishing"):
            self.overlay.hide_now()

    def on_done(self, text: str, audio_ms: int, latency_ms: int):
        if not text.strip():
            self.overlay.hide_now()
            return
        inserter.paste(text)
        history.add(text, audio_ms, self.target_app)
        self.overlay.done()

    def on_error(self, message: str):
        self.keys.reset()
        self.overlay.show_message(message, error=True, ms=5000)

    def open_history(self):
        if history.FILE.exists():
            os.startfile(history.FILE)
        else:
            self.overlay.show_message("No dictations yet", ms=1500)


def mic_icon(color: QColor) -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    body = QPainterPath()
    body.addRoundedRect(22, 6, 20, 34, 10, 10)
    p.fillPath(body, color)
    p.setPen(QPen(color, 5, Qt.SolidLine, Qt.RoundCap))
    p.drawArc(13, 16, 38, 34, 180 * 16, 180 * 16)
    p.drawLine(32, 50, 32, 58)
    p.end()
    return QIcon(pm)


def main():
    # One Murmur at a time: two keyboard hooks would both dictate.
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    mutex = kernel32.CreateMutexW(None, False, "Local\\MurmurDictation")  # noqa: F841 (held until exit)
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        print("Murmur is already running.")
        return
    qt = QApplication(sys.argv)
    qt.setQuitOnLastWindowClosed(False)
    app = App(qt)  # noqa: F841 (kept alive for the event loop)
    sys.exit(qt.exec())


if __name__ == "__main__":
    main()

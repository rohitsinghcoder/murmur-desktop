"""Murmur for Windows: hold the hotkey, speak, release, and your words are typed into the focused app.

    python -m murmur                 # opens the window
    python -m murmur --background    # starts in the tray (used when starting with Windows)
"""
import ctypes
import getpass
import sys
import threading
import time

import numpy as np
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction, QColor, QFont
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import dictation, engine, history, hotkey, inserter, settings
from .pill import Pill
from .ui import style
from .ui.window import MainWindow

INSTANCE = f"MurmurDesktop-{getpass.getuser()}"


class App(QObject):
    # Signals carry events from background threads (hook, mic, decoder) to the UI thread.
    loaded = Signal(float)
    load_failed = Signal(str)
    start = Signal()
    finish = Signal()
    cancel = Signal()
    lock = Signal()
    levels = Signal(list)
    done = Signal(str, int, int)
    error = Signal(str)
    hotkey_recorded = Signal(object)
    speed_result = Signal(str)
    # For the window.
    status_changed = Signal()
    history_changed = Signal()
    hotkey_changed = Signal(list)

    def __init__(self, qt: QApplication):
        super().__init__()
        self.qt = qt
        self.settings = settings.load()
        self.hotkey: list[str] = self.settings["hotkey"]
        self.status, self.status_text = "loading", "Loading speech model…"
        self.load_secs: float | None = None
        self.last_latency_ms: int | None = None
        self.dictation: dictation.Dictation | None = None
        self.target_app: str | None = None
        self.testing_speed = False
        self._told_about_tray = False

        self.pill = Pill()
        self.pill.start_clicked.connect(self.on_click_start)
        self.pill.cancel_clicked.connect(self.on_click_cancel)
        self.pill.stop_clicked.connect(self.on_click_stop)
        self.pill.show()

        self.window = MainWindow(self)

        self.tray = QSystemTrayIcon(style.mic_icon(QColor(150, 150, 160)))
        menu = QMenu()
        menu.addAction("Open Murmur", self.show_window)
        self.status_action = QAction(self.status_text, enabled=False)
        menu.addAction(self.status_action)
        menu.addSeparator()
        menu.addAction("Quit Murmur", self.quit)
        self.menu = menu
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_clicked)
        self.tray.setToolTip("Murmur: loading…")
        self.tray.show()

        self.loaded.connect(self.on_loaded)
        self.load_failed.connect(self.on_load_failed)
        self.start.connect(self.on_start)
        self.finish.connect(self.on_finish)
        self.cancel.connect(self.on_cancel)
        self.lock.connect(self.pill.hands_free)
        self.levels.connect(self.pill.set_level)
        self.done.connect(self.on_done)
        self.error.connect(self.on_error)

        # Hook callbacks must return fast, so they only post to the UI thread.
        self.keys = hotkey.HoldToTalk(
            on_start=self.start.emit, on_finish=self.finish.emit,
            on_cancel=self.cancel.emit, on_lock=self.lock.emit, hotkey=self.hotkey,
        )
        self.keys.start()
        threading.Thread(target=self.load, daemon=True).start()

    # Loading.

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
            rec, on_levels=self.levels.emit, on_done=self.done.emit, on_error=self.error.emit,
        )
        self.loaded.emit(time.perf_counter() - t0)

    def _hint(self) -> str:
        return f"Click or hold {hotkey.describe(self.hotkey)} to dictate"

    def _set_status(self, status: str, text: str):
        self.status, self.status_text = status, text
        self.status_action.setText(text)
        self.status_changed.emit()

    def on_loaded(self, secs: float):
        self.load_secs = secs
        self._set_status("ready", "Ready")
        self.tray.setIcon(style.mic_icon(QColor(style.ACCENT)))
        self.tray.setToolTip(f"Murmur: hold {hotkey.describe(self.hotkey)} to dictate")
        self.pill.ready(self._hint())

    def on_load_failed(self, message: str):
        self._set_status("error", "Couldn't load the speech model")
        self.pill.ready(self._hint())
        self.pill.show_message(f"Couldn't load the speech model: {message}", error=True, ms=8000)

    # Dictation (UI thread).

    def _listen(self, hands_free: bool) -> bool:
        if self.dictation is None:
            self.pill.show_message("Still loading the speech model…", ms=1500)
            return False
        if self.testing_speed or not self.dictation.listen():
            return False
        self.target_app = inserter.foreground_app()
        self.pill.recording(hands_free)
        return True

    def on_start(self):
        self._listen(hands_free=False)

    def on_click_start(self):
        if self._listen(hands_free=True):
            self.keys.hands_free()

    def on_finish(self):
        if self.dictation and self.dictation.busy:
            self.dictation.finish()
            self.pill.processing()

    def on_cancel(self):
        if self.dictation:
            self.dictation.cancel()
        if self.pill.state in ("record", "handsfree", "process"):
            self.pill.rest()

    def on_click_stop(self):
        self.keys.reset()
        self.on_finish()

    def on_click_cancel(self):
        self.keys.reset()
        self.on_cancel()

    def on_done(self, text: str, audio_ms: int, latency_ms: int):
        self.pill.rest()
        self.last_latency_ms = latency_ms
        if text.strip():
            inserter.paste(text)
            history.add(text, audio_ms, self.target_app)
            self.history_changed.emit()
        self.status_changed.emit()

    def on_error(self, message: str):
        self.keys.reset()
        self.pill.show_message(message, error=True, ms=5000)

    # Settings.

    def record_hotkey(self):
        self.keys.record(self.hotkey_recorded.emit)

    def cancel_hotkey_recording(self):
        self.keys.stop_recording()

    def set_hotkey(self, names: list[str]):
        self.hotkey = list(names)
        self.settings["hotkey"] = self.hotkey
        settings.save(self.settings)
        self.keys.set_hotkey(self.hotkey)
        self.pill.set_hint(self._hint())
        self.tray.setToolTip(f"Murmur: hold {hotkey.describe(self.hotkey)} to dictate")
        self.hotkey_changed.emit(self.hotkey)

    def run_speed_test(self):
        def run():
            import soundfile as sf
            wav = engine.MODEL_DIR / "test_wavs" / "1.wav"
            try:
                audio, _ = sf.read(wav, dtype="float32")
                t = engine.Transcriber(engine.load())
                t0 = time.perf_counter()
                for i in range(0, len(audio), engine.SAMPLE_RATE // 10):
                    t.accept(audio[i:i + engine.SAMPLE_RATE // 10])
                t.finish()
                took = time.perf_counter() - t0
                secs = len(audio) / engine.SAMPLE_RATE
                self.speed_result.emit(f"{secs / took:.1f}× faster than real time: {secs:.1f} s of "
                                       f"speech transcribed in {took:.1f} s.")
            except Exception as e:
                self.speed_result.emit(f"The speed test failed: {e}")
            finally:
                self.testing_speed = False

        self.testing_speed = True
        threading.Thread(target=run, daemon=True).start()

    # Window and tray.

    def show_window(self):
        self.window.bring_to_front()

    def _tray_clicked(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.show_window()

    def window_closed(self):
        if not self._told_about_tray:
            self._told_about_tray = True
            self.tray.showMessage("Murmur is still running",
                                  f"Hold {hotkey.describe(self.hotkey)} to dictate. "
                                  "Click the tray icon to open Murmur.",
                                  QSystemTrayIcon.Information, 4000)

    def quit(self):
        self.keys.stop()
        if self.dictation:
            self.dictation.cancel()
        self.tray.hide()
        self.qt.quit()


def main():
    qt = QApplication(sys.argv)
    qt.setQuitOnLastWindowClosed(False)
    qt.setApplicationName("Murmur")
    qt.setFont(QFont("Segoe UI", 10))
    qt.setStyleSheet(style.STYLESHEET)

    # One Murmur at a time: two keyboard hooks would both dictate. A second launch (Start menu,
    # setup.bat) just brings the running one's window to the front.
    probe = QLocalSocket()
    probe.connectToServer(INSTANCE)
    if probe.waitForConnected(500):
        probe.write(b"show")
        probe.waitForBytesWritten(500)
        return
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    mutex = kernel32.CreateMutexW(None, False, "Local\\MurmurDictation")  # noqa: F841 (held until exit)
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS: another copy is still starting
        return

    app = App(qt)
    server = QLocalServer()
    QLocalServer.removeServer(INSTANCE)
    server.listen(INSTANCE)
    server.newConnection.connect(lambda: (server.nextPendingConnection(), app.show_window()))

    if "--background" not in sys.argv:
        app.show_window()
    sys.exit(qt.exec())


if __name__ == "__main__":
    main()

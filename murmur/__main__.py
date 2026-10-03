"""Murmur for Windows: hold the hotkey, speak, release, and your words are typed into the focused app.

    python -m murmur                 # opens the window
    python -m murmur --background    # starts in the tray (used when starting with Windows)
"""
import ctypes
import getpass
import logging
import os
import sys
import threading
import time
import traceback

import numpy as np
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QAction, QFont
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import (casing, dictation, engine, fixes, history, hotkey, inserter, learn, logfile, mics, pipeline,
               settings, sounds, spacing, vocabulary)
from .pill import Pill
from .ui import style
from .ui.window import MainWindow  # imports Qt WebEngine, which must happen before QApplication

INSTANCE = f"MurmurDesktop-{getpass.getuser()}"
log = logging.getLogger("murmur.app")
# A dictation shorter than this that heard nothing was most likely a stray press: no message.
NOTHING_HEARD_MIN_MS = 600
# Dictations in the tray's Recent menu, and how much of each it shows.
RECENT = 5
# Minutes the closed window is kept before it's released, and (with "save_memory" on) minutes
# without dictating before the speech model is unloaded. It loads again while you speak.
RELEASE_WINDOW_MIN = 5
IDLE_UNLOAD_MIN = 10
RECENT_CHARS = 48


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
    silent = Signal()
    auto_stopped = Signal()
    hotkey_recorded = Signal(object)
    speed_result = Signal(str)
    # For the window.
    status_changed = Signal()
    history_changed = Signal()
    hotkey_changed = Signal(list)
    theme_changed = Signal(str)  # the theme in effect: light or dark
    paused_changed = Signal(bool)
    fix_found = Signal(object)  # a learn.Fix the user made to a dictation (fixes.py)

    def __init__(self, qt: QApplication):
        super().__init__()
        self.qt = qt
        self.settings = settings.load()
        self.hotkey: list[str] = self.settings["hotkey"]
        self.theme_setting: str = self.settings["theme"]
        self.theme = self._resolve_theme()
        qt.setStyleSheet(style.menu_stylesheet(self.theme))
        # With "system", follow Windows when its app theme changes.
        qt.styleHints().colorSchemeChanged.connect(lambda _: self._apply_theme())
        self.status, self.status_text = "loading", "Loading speech model…"
        self.load_secs: float | None = None
        self.last_latency_ms: int | None = None
        self.dictation: dictation.Dictation | None = None
        self.target_app: str | None = None
        self.testing_speed = False
        self.paused = False  # from the tray: the hotkey and the bar don't dictate
        self._told_about_tray = False
        # For a space between dictations: what's before the caret, or else where the last one went.
        self.caret = spacing.CaretReader()
        self._caret_read = (None, 0.0)  # (read in progress, when it started)
        self.last_insert = spacing.LastInsert()
        # Watches the last dictation for words the user fixes, to learn them (with "learn_fixes").
        self.fixes = fixes.Watcher(self.caret, self.fix_found.emit)
        self._fixes_timer = QTimer(self, interval=500, timeout=self._poll_fixes)

        self.pill = Pill()
        self.pill.start_clicked.connect(self.on_click_start)
        self.pill.cancel_clicked.connect(self.on_click_cancel)
        self.pill.stop_clicked.connect(self.on_click_stop)
        self.pill.show()
        self.sounds = sounds.Sounds()
        # With "save_memory" on, the model is unloaded after a while without dictating.
        self._idle_timer = QTimer(self, singleShot=True, interval=IDLE_UNLOAD_MIN * 60_000,
                                  timeout=self._idle)
        self.apply_settings()

        # Created the first time it's opened: the web view costs ~100 MB, and when Murmur starts
        # with Windows it often never is.
        self.window: MainWindow | None = None
        # Closed for a while, the window is released to free its memory (MainWindow.release).
        self._release_timer = QTimer(self, singleShot=True, interval=RELEASE_WINDOW_MIN * 60_000,
                                     timeout=self._release_window)

        self.tray = QSystemTrayIcon(style.logo_icon(gray=True))
        menu = QMenu()
        menu.addAction("Open Murmur", self.show_window)
        self.status_action = QAction(self.status_text, enabled=False)
        menu.addAction(self.status_action)
        menu.addSeparator()
        self.paste_last_action = menu.addAction("Paste last dictation", self.paste_last)
        self.copy_last_action = menu.addAction("Copy last dictation", self.copy_last)
        self.recent_menu = menu.addMenu("Recent")
        menu.addSeparator()
        self.pause_action = menu.addAction("Pause Murmur", lambda: self.set_paused(not self.paused))
        menu.addAction("Quit Murmur", self.quit)
        menu.aboutToShow.connect(self._fill_menu)
        self.menu = menu
        # The menu takes focus; "Paste last dictation" goes back to the app the user was in.
        self.last_window = inserter.LastAppWindow()
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_clicked)
        self._update_tray()
        self.tray.show()

        self.loaded.connect(self.on_loaded)
        self.load_failed.connect(self.on_load_failed)
        self.start.connect(self.on_start)
        self.finish.connect(self.on_finish)
        self.cancel.connect(self.on_cancel)
        self.lock.connect(self.on_lock)
        self.levels.connect(self.pill.set_level)
        self.done.connect(self.on_done)
        self.error.connect(self.on_error)
        self.silent.connect(self.on_silent)
        self.auto_stopped.connect(self.on_click_stop)  # as if ■ was clicked
        self.fix_found.connect(self._learn)

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
            engine.transcribe(rec, np.zeros(engine.SAMPLE_RATE, dtype=np.float32))
        except Exception as e:
            log.exception("Couldn't load the speech model")
            self.load_failed.emit(str(e))
            return
        log.info("Speech model loaded in %.1f s", time.perf_counter() - t0)
        self.dictation = dictation.Dictation(
            rec, on_levels=self.levels.emit, on_done=self.done.emit, on_error=self.error.emit,
            on_silent=self.silent.emit, on_auto_stop=self.auto_stopped.emit,
            tidy=lambda text: pipeline.process(text, self.settings),
            device=mics.find(self.settings["microphone"]),
            vocab=vocabulary.Vocabulary(vocabulary.terms(self.settings)),
        )
        self.loaded.emit(time.perf_counter() - t0)

    def _hint(self) -> str:
        if self.paused:
            return "Murmur is paused. Click to resume"
        return f"Click or hold {hotkey.describe(self.hotkey)} to dictate"

    def _set_status(self, status: str, text: str):
        self.status, self.status_text = status, text
        self.status_action.setText(text)
        self.status_changed.emit()

    def on_loaded(self, secs: float):
        self.load_secs = secs
        self._set_status("ready", "Ready")
        self._update_tray()
        self.pill.ready(self._hint())

    def on_load_failed(self, message: str):
        self._set_status("error", "Couldn't load the speech model")
        self._update_tray()
        self.pill.ready(self._hint())
        # The details are in the log; the bar has room for a line.
        self.pill.show_message("Couldn't load the speech model.", error=True, ms=10000,
                               action="Open log", on_click=self.open_log)

    # Dictation (UI thread).

    def _listen(self, hands_free: bool) -> bool:
        if self.paused:
            self.pill.show_message("Murmur is paused.", ms=4000, action="Resume",
                                   on_click=lambda: self.set_paused(False))
            return False
        if self.dictation is None:
            self.pill.show_message("Still loading the speech model…", ms=1500)
            return False
        if self.testing_speed or not self.dictation.listen(hands_free):
            return False
        self.target_app = inserter.foreground_app()
        self.fixes.finish()  # its last look at the previous dictation, before this one is pasted
        self.pill.recording(hands_free)
        self.sounds.start()
        if self.settings["save_memory"]:
            self._idle_timer.start()  # counts from the latest dictation
        return True

    def on_start(self):
        self._listen(hands_free=False)

    def on_click_start(self):
        if self.paused:  # the dimmed bar says "Click to resume"
            self.set_paused(False)
            self.pill.show_message("Murmur is on again", ms=1600)
            return
        if self._listen(hands_free=True):
            self.keys.hands_free()

    def on_lock(self):
        # Double tap: now hands-free, so it may finish by itself after a long silence.
        if self.dictation and self.dictation.busy:
            self.dictation.hands_free = True
        self.pill.hands_free()

    def on_finish(self):
        if self.dictation and self.dictation.busy:
            self.dictation.finish()
            self.pill.processing()
            # Asks the app what's before the caret while the transcription is finished.
            self._caret_read = (self.caret.start(), time.monotonic())
            self.sounds.stop()

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
        if text.strip() or "\n" in text:  # just "\n" is "new line" said on its own
            read, self._caret_read = self._caret_read, (None, 0.0)
            how, text = self._insert(text, *read)
            # Lengths and timings only: never what was said.
            log.info("Dictated %d chars (%d ms audio, ready in %d ms) into %s by %s",
                     len(text), audio_ms, latency_ms, self.target_app, how)
            history.add(text, audio_ms, self.target_app)
            self.history_changed.emit()
        elif audio_ms >= NOTHING_HEARD_MIN_MS:
            self.pill.show_message("Didn't catch that", ms=1800)
        self.status_changed.emit()

    def _insert(self, text: str, read, read_started: float) -> tuple[str, str]:
        """Types text into the focused app, after a space if it would run into what's there, and
        without the capital if it carries on a sentence. Returns how, and the text as typed."""
        window = inserter.focus_window()
        before = self.caret.result(read, read_started)
        if text not in {out for _, out in self.settings["snippets"]}:  # those are typed as written
            text = casing.continue_sentence(text, before, keep=vocabulary.terms(self.settings))
        follows = self.last_insert.follows(window, self.keys.typed_at, time.monotonic())
        space = spacing.needs_space(text, before, follows)
        how = inserter.paste(text, space_before=space)
        if how == "copy":
            self.pill.show_message("Can't type into apps run as administrator. Copied instead.", ms=5000)
        else:
            self.last_insert.record(window, time.monotonic())
            self.pill.done()
            if window and self.settings["learn_fixes"]:
                QTimer.singleShot(250, lambda: self._watch_fixes(text, window[0]))
        return how + (" after a space" if space else ""), text

    # Learning from the user's fixes (fixes.py, learn.py).

    def _watch_fixes(self, text: str, window: int):
        self.fixes.finish()
        self.fixes.start(text, window)
        self._fixes_timer.start()

    def _poll_fixes(self):
        """Reads the watched text again once the user has typed in its window and paused; a last
        time when they've left it or the watch is up."""
        now = time.monotonic()
        focus = inserter.focus_window()
        if (not self.fixes.active or now - self.fixes.started > fixes.WATCH_S
                or not focus or focus[0] != self.fixes.window):
            self.fixes.finish()
            self._fixes_timer.stop()
        elif self.keys.typed_at > self.fixes.read_at and now - self.keys.typed_at >= fixes.IDLE_S:
            self.fixes.check()

    def _learn(self, fix):
        """A word the user fixed by hand: written their way from now on (learn.learning)."""
        if not self.settings["learn_fixes"]:
            return
        change = learn.learning(self.settings, fix)
        settings.save(self.settings)  # what learn.learning remembered, even if nothing changes
        if change is None:
            return
        option, value, undo_value = change
        learn.mark(self.settings, fix.write)  # shown as learned on the Words page
        self.set_option(option, value)
        log.info("Learned a fix the user made (%s)", option)

        def undo():
            learn.unmark(self.settings, fix.write)
            learn.reject(self.settings, fix)
            self.set_option(option, undo_value(self.settings[option]))

        if self.pill.state not in ("record", "handsfree", "process"):
            self.pill.show_message(f"Learned “{fix.write}”", ms=6000, action="Undo", on_click=undo)

    def on_error(self, message: str):
        log.error("%s", message)
        self.keys.reset()
        self.pill.show_message(message, error=True, ms=5000)

    def on_silent(self):
        # Usually Windows' microphone privacy setting, or a muted mic. Clicking opens the setting.
        self.keys.reset()
        self.pill.show_message("Microphone is silent.", error=True, ms=7000, action="Check access",
                               on_click=lambda: os.startfile("ms-settings:privacy-microphone"))

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
        self._update_tray()
        self.hotkey_changed.emit(self.hotkey)

    def set_option(self, key: str, value):
        """A setting from the window (see settings.OPTIONS). Dictation reads them as it goes."""
        if not settings.valid(key, value):
            return
        self.settings[key] = value
        settings.save(self.settings)
        self.apply_settings()
        self.status_changed.emit()

    def apply_settings(self):
        """Hands the settings to the parts that use them: at start and after every change."""
        history.keep = self.settings["keep_history"]
        history.prune()
        self.history_changed.emit()
        self.sounds.set_enabled(self.settings["sounds"])
        if self.settings["save_memory"]:
            if not self._idle_timer.isActive():
                self._idle_timer.start()
        else:
            self._idle_timer.stop()
            if self.dictation:
                self.dictation.preload()  # turned off while unloaded: bring it back now
        self.pill.set_show_idle(self.settings["show_bar"])
        if self.dictation:
            self.dictation.vocab = vocabulary.Vocabulary(vocabulary.terms(self.settings))
            # A microphone that isn't connected falls back to the default until it's back.
            device = mics.find(self.settings["microphone"])
            if device != self.dictation.device:
                self.dictation.device = device
                if not self.dictation.busy:
                    self.dictation.close()  # the stream kept open is the old mic's

    def _resolve_theme(self) -> str:
        return style.system_theme() if self.theme_setting == "system" else self.theme_setting

    def set_theme(self, setting: str):
        if setting not in ("system", "light", "dark"):
            return
        self.theme_setting = setting
        self.settings["theme"] = setting
        settings.save(self.settings)
        self._apply_theme()
        self.status_changed.emit()  # the page shows which option is chosen

    def _apply_theme(self):
        theme = self._resolve_theme()
        if theme == self.theme:
            return
        self.theme = theme
        self.qt.setStyleSheet(style.menu_stylesheet(theme))
        self.theme_changed.emit(theme)

    def run_speed_test(self):
        def run():
            import soundfile as sf
            wav = engine.MODEL_DIR / "test_wavs" / "0.wav"
            try:
                audio, _ = sf.read(wav, dtype="float32")
                t0 = time.perf_counter()
                self.dictation.transcribe(audio)
                took = time.perf_counter() - t0
                secs = len(audio) / engine.SAMPLE_RATE
                self.speed_result.emit(f"{secs / took:.0f}× faster than real time: {secs:.1f} s of "
                                       f"speech transcribed in {took * 1000:.0f} ms.")
            except Exception as e:
                self.speed_result.emit(f"The speed test failed: {e}")
            finally:
                self.testing_speed = False

        self.testing_speed = True
        threading.Thread(target=run, daemon=True).start()

    # Window and tray.

    def show_window(self):
        self._release_timer.stop()
        if self.window is None:
            self.window = MainWindow(self)
        self.window.bring_to_front()

    def _release_window(self):
        if self.window is not None and not self.window.isVisible():
            self.window.release()
            self.window = None
            log.info("Released the closed window")

    def _idle(self):
        if not (self.settings["save_memory"] and self.dictation):
            return
        if self.dictation.busy:
            self._idle_timer.start()
        else:
            self.dictation.unload()

    def _tray_clicked(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.show_window()

    def _update_tray(self):
        if self.paused:
            tip = "Murmur: paused"
        elif self.status == "ready":
            tip = f"Murmur: hold {hotkey.describe(self.hotkey)} to dictate"
        else:
            tip = f"Murmur: {self.status_text[0].lower()}{self.status_text[1:]}"
        self.tray.setIcon(style.logo_icon(gray=self.paused or self.status != "ready"))
        self.tray.setToolTip(tip)

    def _fill_menu(self):
        entries = history.load()[:RECENT]
        self.paste_last_action.setEnabled(bool(entries))
        self.copy_last_action.setEnabled(bool(entries))
        self.recent_menu.setEnabled(bool(entries))
        self.recent_menu.clear()
        for entry in entries:
            text = entry.get("text", "")
            label = " ".join(text.split())
            if len(label) > RECENT_CHARS:
                label = label[:RECENT_CHARS - 1].rstrip() + "…"
            self.recent_menu.addAction(label.replace("&", "&&"), lambda text=text: self.copy_text(text))

    def _last_text(self) -> str | None:
        entries = history.load()
        return entries[0].get("text") if entries else None

    def copy_text(self, text: str):
        if inserter.copy(text):
            self.pill.show_message("Copied", ms=1200)

    def copy_last(self):
        if text := self._last_text():
            self.copy_text(text)

    def paste_last(self):
        text = self._last_text()
        if not text:
            return
        # Back to the app the user was in before the tray menu, then paste once it has focus.
        if not self.last_window.activate():
            if inserter.copy(text):
                self.pill.show_message("Couldn't get back to the app. Copied instead.", ms=3000)
            return
        QTimer.singleShot(150, lambda: log.info("Pasted the last dictation again by %s",
                                                self._insert(text, self.caret.start(), time.monotonic())[0]))

    def set_paused(self, paused: bool):
        """Paused, the hotkey and the bar don't dictate (until resumed from the tray)."""
        self.paused = paused
        self.keys.pause(paused)
        if paused and self.dictation and self.dictation.busy:
            self.on_cancel()
        self.pause_action.setText("Resume Murmur" if paused else "Pause Murmur")
        self._update_tray()
        self.pill.set_paused(paused, self._hint())
        log.info("Paused" if paused else "Resumed")
        self.paused_changed.emit(paused)

    def open_log(self):
        os.startfile(logfile.FILE if logfile.FILE.exists() else logfile.FILE.parent)

    def window_closed(self):
        self._release_timer.start()
        if not self._told_about_tray:
            self._told_about_tray = True
            self.tray.showMessage("Murmur is still running",
                                  f"Hold {hotkey.describe(self.hotkey)} to dictate. "
                                  "Click the tray icon to open Murmur.",
                                  QSystemTrayIcon.Information, 4000)

    def quit(self):
        log.info("Murmur quitting")
        # Once asked to quit, nothing may keep Murmur running: a half-quit one has no hotkey and
        # no tray icon, yet holds the single-instance lock, so a new one can't start either.
        threading.Thread(target=_exit_if_stuck, name="murmur-quit", daemon=True).start()
        for step in (self.keys.stop, self._stop_dictation, self.tray.hide):
            try:
                step()
            except Exception:
                log.exception("Couldn't %s while quitting", step.__name__)
        self.qt.quit()

    def _stop_dictation(self):
        if self.dictation:
            self.dictation.cancel()
            self.dictation.close()


# Seconds Murmur may take to quit before it's ended anyway.
QUIT_GRACE_S = 4


def _exit_if_stuck():
    """Ends Murmur if quitting hangs, with every thread's stack in the log to show where."""
    time.sleep(QUIT_GRACE_S)
    stacks = "\n".join(f"Thread {threading._active.get(tid, tid)}:\n{''.join(traceback.format_stack(frame))}"
                       for tid, frame in sys._current_frames().items())
    log.error("Still running %d s after quitting; ending it. Threads:\n%s", QUIT_GRACE_S, stacks)
    logging.shutdown()
    os._exit(1)


def main():
    # Its own taskbar identity, so Windows shows Murmur's icon rather than Python's.
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Murmur.Desktop")
    qt = QApplication(sys.argv)
    qt.setQuitOnLastWindowClosed(False)
    qt.setApplicationName("Murmur")
    qt.setWindowIcon(style.logo_icon())
    style.load_fonts()
    qt.setFont(QFont("Geist", 10))

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

    logfile.setup()
    log.info("Murmur starting (Python %s)", sys.version.split()[0])
    app = App(qt)
    server = QLocalServer()
    QLocalServer.removeServer(INSTANCE)
    server.listen(INSTANCE)
    server.newConnection.connect(lambda: (server.nextPendingConnection(), app.show_window()))

    if "--background" not in sys.argv:
        app.show_window()
    code = qt.exec()
    log.info("Murmur stopped")
    # Straight out: Python's exit would wait for worker threads (decoder, UI Automation, audio),
    # and one stuck in another app's UI Automation would keep Murmur alive. Everything worth
    # keeping (settings, history) is already written.
    logging.shutdown()
    os._exit(code)


if __name__ == "__main__":
    main()

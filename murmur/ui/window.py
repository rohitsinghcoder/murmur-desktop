"""Murmur's window: the HTML interface in ui/web, shown in a Qt WebEngine (Chromium) view.

The page talks to Murmur through `Bridge` over QWebChannel.
"""
import json
import os
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QColor, QDesktopServices, QGuiApplication
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QVBoxLayout, QWidget

from .. import engine, history, startup
from .. import hotkey as hk
from . import style

WEB = Path(__file__).resolve().parent / "web"
VERSION = "0.3.0"
REPO = "https://github.com/rohitsinghcoder/murmur-desktop"
DEFAULT_HOTKEY = ["rctrl"]


class Bridge(QObject):
    """What the page can ask of Murmur, and what Murmur tells the page."""

    stateChanged = Signal()
    historyChanged = Signal()
    hotkeyRecorded = Signal(str)
    speedResult = Signal(str)
    startupChanged = Signal(str)  # an error message, or "" when it worked

    def __init__(self, app):
        super().__init__()
        self.app = app
        app.status_changed.connect(self.stateChanged)
        app.hotkey_changed.connect(lambda _: self.stateChanged.emit())
        app.history_changed.connect(self.historyChanged)
        app.hotkey_recorded.connect(self._recorded)
        app.speed_result.connect(self.speedResult)
        app.theme_changed.connect(lambda _: self.stateChanged.emit())

    @Slot(result=str)
    def state(self) -> str:
        a = self.app
        return json.dumps({
            "hotkey": [hk.label(k) for k in a.hotkey],
            "hotkeyText": hk.describe(a.hotkey),
            "isDefaultHotkey": a.hotkey == DEFAULT_HOTKEY,
            "status": a.status,
            "statusText": a.status_text,
            "version": VERSION,
            "model": engine.MODEL_LABEL,
            "loadSecs": a.load_secs,
            "lastLatencyMs": a.last_latency_ms,
            "dataDir": str(history.DIR),
            "theme": a.theme_setting,
            "resolvedTheme": a.theme,
            "startup": startup.enabled(),
        })

    @Slot(result=str)
    def history(self) -> str:
        entries = history.load()
        return json.dumps({"entries": entries, "stats": history.stats(entries)}, ensure_ascii=False)

    @Slot(str)
    def copy(self, text: str):
        QGuiApplication.clipboard().setText(text)

    @Slot(float)
    def deleteEntry(self, entry_time: float):
        history.delete(int(entry_time))
        self.historyChanged.emit()

    @Slot()
    def recordHotkey(self):
        self.app.record_hotkey()

    @Slot()
    def cancelHotkey(self):
        self.app.cancel_hotkey_recording()

    @Slot()
    def resetHotkey(self):
        self.app.set_hotkey(DEFAULT_HOTKEY)

    @Slot(str)
    def setTheme(self, setting: str):
        self.app.set_theme(setting)

    @Slot(bool)
    def setStartup(self, on: bool):
        # PowerShell makes the shortcut, which takes a moment: not on the UI thread.
        def run():
            try:
                startup.set_enabled(on)
                self.startupChanged.emit("")
            except Exception as e:
                self.startupChanged.emit(str(e) or "failed")

        threading.Thread(target=run, daemon=True).start()

    @Slot()
    def speedTest(self):
        self.app.run_speed_test()

    @Slot()
    def openDataFolder(self):
        history.DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(history.DIR)

    @Slot()
    def openRepo(self):
        QDesktopServices.openUrl(QUrl(REPO))

    def _recorded(self, vks):
        if not vks:
            self.hotkeyRecorded.emit(json.dumps({"cancelled": True}))
            return
        names = hk.from_pressed(vks)
        reason = hk.problem(names)
        if reason:
            self.hotkeyRecorded.emit(json.dumps({"error": f"{hk.describe(names)}: {reason}"}))
            return
        self.app.set_hotkey(names)
        self.hotkeyRecorded.emit(json.dumps({"ok": True, "hotkeyText": hk.describe(names)}))


class MainWindow(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setWindowTitle("Murmur")
        self.setWindowIcon(style.logo_icon())
        self.resize(1080, 720)
        self.setMinimumSize(880, 600)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.view = QWebEngineView(self)
        # Off the record: no cache or cookies written to disk. Created after the view, so the
        # page (owned by the view) is destroyed before its profile.
        self.profile = QWebEngineProfile(self)
        page = QWebEnginePage(self.profile, self.view)
        self.view.setPage(page)
        self.view.setContextMenuPolicy(Qt.NoContextMenu)
        self.bridge = Bridge(app)
        self.channel = QWebChannel(page)
        self.channel.registerObject("murmur", self.bridge)
        page.setWebChannel(self.channel)
        # The theme rides in the URL so the first frame is already in it (no flash).
        url = QUrl.fromLocalFile(str(WEB / "index.html"))
        url.setQuery(f"theme={app.theme}")
        self._apply_theme(app.theme)
        app.theme_changed.connect(self._apply_theme)
        page.load(url)
        lay.addWidget(self.view)

    def _apply_theme(self, theme: str):
        # The page eases its own colours; the frame and the fill behind the page follow.
        self.setStyleSheet(f"background: {style.BG[theme]};")
        self.view.page().setBackgroundColor(QColor(style.BG[theme]))
        if self.isVisible():
            style.title_bar(self, theme)

    def bring_to_front(self):
        if self.isMinimized():
            self.showNormal()
        self.show()
        style.title_bar(self, self.app.theme)
        self.raise_()
        self.activateWindow()
        self.bridge.historyChanged.emit()

    def closeEvent(self, event):
        # Closing the window keeps Murmur running in the tray, like Wispr Flow.
        event.ignore()
        self.app.cancel_hotkey_recording()
        self.bridge.hotkeyRecorded.emit(json.dumps({"cancelled": True}))
        self.hide()
        self.app.window_closed()

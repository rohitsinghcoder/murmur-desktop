"""Home: stats, a try-it box, and your dictation history grouped by day."""
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from .. import history
from .. import hotkey as hk
from . import style
from .widgets import Chips, card, clear, icon_button, label, page

MAX_SHOWN = 200


def _day_name(day: tuple) -> str:
    today = time.localtime()[:3]
    yesterday = time.localtime(time.time() - 86400)[:3]
    if day == today:
        return "TODAY"
    if day == yesterday:
        return "YESTERDAY"
    t = time.mktime((*day, 12, 0, 0, 0, 0, -1))
    return time.strftime("%A, %d %B", time.localtime(t)).upper()


def _clock(ms: int) -> str:
    return time.strftime("%I:%M %p", time.localtime(ms / 1000)).lstrip("0")


class Entry(QFrame):
    """One dictation: time, text, app; copy and delete show on hover."""

    def __init__(self, entry: dict, on_delete):
        super().__init__()
        self.setObjectName("Entry")
        self.entry = entry
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 10, 8, 10)
        lay.setSpacing(14)

        when = label(_clock(entry.get("time", 0)), "Faint")
        when.setFixedWidth(64)
        lay.addWidget(when, 0, Qt.AlignTop)

        text = QVBoxLayout()
        text.setSpacing(3)
        body = label(entry.get("text", ""), wrap=True)
        body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        text.addWidget(body)
        meta = []
        if entry.get("app"):
            meta.append(entry["app"].removesuffix(".exe"))
        if entry.get("audioMs"):
            meta.append(f"{entry['audioMs'] / 1000:.0f}s")
        if meta:
            text.addWidget(label(" · ".join(meta), "Faint"))
        lay.addLayout(text, 1)

        self.copy = icon_button("copy", "Copy")
        self.copy.clicked.connect(self._copy)
        self.remove = icon_button("delete", "Delete")
        self.remove.clicked.connect(lambda: on_delete(entry))
        for b in (self.copy, self.remove):
            b.setVisible(False)
            lay.addWidget(b, 0, Qt.AlignTop)

    def _copy(self):
        QGuiApplication.clipboard().setText(self.entry.get("text", ""))
        self.copy.setText(style.ICONS["check"])
        QTimer.singleShot(1200, lambda: self.copy.setText(style.ICONS["copy"]))

    def enterEvent(self, event):
        self.copy.setVisible(True)
        self.remove.setVisible(True)

    def leaveEvent(self, event):
        self.copy.setVisible(False)
        self.remove.setVisible(False)


class HomePage(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        outer, lay = page("Welcome back")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(outer)

        hint = QHBoxLayout()
        hint.setSpacing(6)
        hint.addWidget(label("Hold", "Dim"))
        self.chips = Chips(app.hotkey)
        hint.addWidget(self.chips)
        hint.addWidget(label("in any app to dictate. Double-tap for hands-free, Esc to cancel.", "Dim"))
        hint.addStretch(1)
        lay.addLayout(hint)
        lay.addSpacing(6)

        stats = QHBoxLayout()
        stats.setSpacing(12)
        self.stat_values = {}
        for key, name in [("words", "Words dictated"), ("wpm", "Words per minute"),
                          ("dictations", "Dictations"), ("streak", "Day streak")]:
            frame, box = card(spacing=2, margins=(16, 14, 16, 14))
            value = label("0", "StatValue")
            box.addWidget(value)
            box.addWidget(label(name, "Dim"))
            self.stat_values[key] = value
            stats.addWidget(frame, 1)
        lay.addLayout(stats)

        self.try_it = QLineEdit()
        lay.addWidget(self.try_it)
        lay.addSpacing(10)

        header = QHBoxLayout()
        header.addWidget(label("History", font=style.heading_font(13)))
        header.addStretch(1)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search")
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(240)
        self.search.addAction(_search_icon(), QLineEdit.LeadingPosition)
        header.addWidget(self.search)
        lay.addLayout(header)

        self.list = QVBoxLayout()
        self.list.setSpacing(2)
        lay.addLayout(self.list)
        lay.addStretch(1)

        self._debounce = QTimer(self, singleShot=True, interval=150, timeout=self.refresh)
        self.search.textChanged.connect(self._debounce.start)
        self.set_hotkey(app.hotkey)

    def set_hotkey(self, hotkey: list[str]):
        self.chips.set(hotkey)
        self.try_it.setPlaceholderText(f"Try it: click here, hold {hk.describe(hotkey)} and speak")

    def refresh(self):
        entries = history.load()
        s = history.stats(entries)
        self.stat_values["words"].setText(f"{s['words']:,}")
        self.stat_values["wpm"].setText(str(s["wpm"]) if s["wpm"] else "–")
        self.stat_values["dictations"].setText(f"{s['dictations']:,}")
        self.stat_values["streak"].setText(str(s["streak"]))

        query = self.search.text().strip().lower()
        if query:
            entries = [e for e in entries if query in e.get("text", "").lower()]
        clear(self.list)

        if not entries:
            frame, box = card(margins=(18, 28, 18, 28))
            box.addWidget(label("No matches." if query else
                                "Your dictations will show up here.", "Dim"), 0, Qt.AlignCenter)
            self.list.addWidget(frame)
            return
        day = None
        for e in entries[:MAX_SHOWN]:
            d = time.localtime(e.get("time", 0) / 1000)[:3]
            if d != day:
                day = d
                group = label(_day_name(d), "Group")
                group.setContentsMargins(12, 14 if self.list.count() else 4, 0, 4)
                self.list.addWidget(group)
            self.list.addWidget(Entry(e, self._delete))
        if len(entries) > MAX_SHOWN:
            more = label(f"Showing the latest {MAX_SHOWN}. Search to find older dictations.", "Faint")
            more.setContentsMargins(12, 10, 0, 0)
            self.list.addWidget(more)

    def _delete(self, entry: dict):
        history.delete(entry.get("time"))
        self.refresh()


def _search_icon() -> QIcon:
    pm = QPixmap(32, 32)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setFont(style.icon_font(14))
    p.setPen(QColor(style.FAINT))
    p.drawText(pm.rect(), Qt.AlignCenter, style.ICONS["search"])
    p.end()
    return QIcon(pm)

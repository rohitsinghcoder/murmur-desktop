"""Murmur's main window: a sidebar with Home, Settings and About."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QButtonGroup, QHBoxLayout, QLabel, QPushButton, QStackedWidget,
                               QVBoxLayout, QWidget)

from . import style
from .about import AboutPage
from .home import HomePage
from .settings_page import SettingsPage
from .widgets import Chips, glyph, label

STATUS_COLORS = {"loading": style.DIM, "ready": style.GOOD, "error": style.DANGER}


class NavButton(QPushButton):
    def __init__(self, icon: str, text: str):
        super().__init__()
        self.setObjectName("Nav")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(36)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 10, 0)
        lay.setSpacing(12)
        self.icon = glyph(icon, 11, None)
        self.text_label = label(text)
        self.text_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        lay.addWidget(self.icon)
        lay.addWidget(self.text_label, 1)
        self.toggled.connect(self._color)
        self._color(False)

    def _color(self, on: bool):
        color = style.TEXT if on else style.DIM
        for lbl in (self.icon, self.text_label):
            lbl.setStyleSheet(f"color: {color};")


class MainWindow(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setObjectName("Root")
        self.setWindowTitle("Murmur")
        self.setWindowIcon(style.mic_icon(QColor(style.TEXT), QColor("#1f1b33")))
        self.resize(980, 680)
        self.setMinimumSize(820, 560)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(216)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(14, 18, 14, 16)
        side.setSpacing(4)

        brand = QHBoxLayout()
        brand.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(style.mic_icon(QColor(style.TEXT), QColor("#1f1b33")).pixmap(28, 28))
        brand.addWidget(logo)
        brand.addWidget(label("Murmur", font=style.heading_font(13)))
        brand.addStretch(1)
        side.addLayout(brand)
        side.addSpacing(18)

        self.stack = QStackedWidget()
        self.home = HomePage(app)
        self.settings = SettingsPage(app)
        self.about = AboutPage(app)
        self.nav = QButtonGroup(self)
        for i, (icon, text, page) in enumerate([("home", "Home", self.home),
                                                ("settings", "Settings", self.settings),
                                                ("info", "About", self.about)]):
            b = NavButton(icon, text)
            self.nav.addButton(b, i)
            side.addWidget(b)
            self.stack.addWidget(page)
        self.nav.idClicked.connect(self.show_page)
        self.nav.button(0).setChecked(True)
        side.addStretch(1)

        hint = QHBoxLayout()
        hint.setSpacing(6)
        hint.addWidget(label("Hold", "Faint"))
        self.side_chips = Chips(app.hotkey)
        hint.addWidget(self.side_chips)
        hint.addStretch(1)
        side.addLayout(hint)
        side.addSpacing(8)
        status = QHBoxLayout()
        status.setSpacing(8)
        self.status_dot = label("●")
        self.status_text = label("", "Dim")
        status.addWidget(self.status_dot)
        status.addWidget(self.status_text, 1)
        side.addLayout(status)

        root.addWidget(sidebar)
        root.addWidget(self.stack, 1)

        app.status_changed.connect(self.refresh_status)
        app.history_changed.connect(self.home.refresh)
        app.hotkey_changed.connect(self.set_hotkey)
        self.refresh_status()
        self.home.refresh()
        self.about.refresh()

    def show_page(self, index: int):
        self.settings.stop_recording()
        self.nav.button(index).setChecked(True)
        self.stack.setCurrentIndex(index)
        if index == 0:
            self.home.refresh()

    def refresh_status(self):
        self.status_dot.setStyleSheet(f"color: {STATUS_COLORS[self.app.status]}; font-size: 8pt;")
        self.status_text.setText(self.app.status_text)

    def set_hotkey(self, hotkey: list[str]):
        self.side_chips.set(hotkey)
        self.home.set_hotkey(hotkey)

    def bring_to_front(self):
        if self.isMinimized():
            self.showNormal()
        self.show()
        style.dark_title_bar(self)
        self.raise_()
        self.activateWindow()
        self.home.refresh()

    def closeEvent(self, event):
        # Closing the window keeps Murmur running in the tray, like Wispr Flow.
        event.ignore()
        self.settings.stop_recording()
        self.hide()
        self.app.window_closed()

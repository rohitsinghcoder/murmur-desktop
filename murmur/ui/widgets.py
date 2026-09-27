"""Small building blocks shared by the pages."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QScrollArea, QToolButton, QVBoxLayout,
                               QWidget)

from .. import hotkey as hk
from . import style

CONTENT_WIDTH = 760


def label(text: str = "", name: str | None = None, font=None, wrap=False) -> QLabel:
    lbl = QLabel(text)
    if name:
        lbl.setObjectName(name)
    if font:
        lbl.setFont(font)
    lbl.setWordWrap(wrap)
    return lbl


def glyph(key: str, size=11, name: str | None = "Dim") -> QLabel:
    lbl = label(style.ICONS[key], name, style.icon_font(size))
    lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
    return lbl


def icon_button(key: str, tooltip: str) -> QToolButton:
    b = QToolButton()
    b.setObjectName("Icon")
    b.setFont(style.icon_font(10))
    b.setText(style.ICONS[key])
    b.setToolTip(tooltip)
    b.setCursor(Qt.PointingHandCursor)
    return b


def clear(layout):
    """Removes every widget from a layout. Hidden right away: deleteLater alone would leave them
    drawn on top of their replacements until the next event loop pass."""
    while layout.count():
        w = layout.takeAt(0).widget()
        if w:
            w.hide()
            w.deleteLater()


def card(spacing=0, margins=(18, 16, 18, 16)) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("Card")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(*margins)
    lay.setSpacing(spacing)
    return frame, lay


def divider() -> QFrame:
    d = QFrame()
    d.setObjectName("Divider")
    return d


class Chips(QWidget):
    """A hotkey drawn as keyboard keys: [Ctrl] + [Shift] + [Space]."""

    def __init__(self, hotkey: list[str] | None = None):
        super().__init__()
        self.lay = QHBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(5)
        if hotkey:
            self.set(hotkey)

    def set(self, hotkey: list[str]):
        clear(self.lay)
        for i, name in enumerate(hotkey):
            if i:
                self.lay.addWidget(label("+", "Faint"))
            self.lay.addWidget(label(hk.label(name), "Chip"))


def page(title: str) -> tuple[QWidget, QVBoxLayout]:
    """A scrolling page with a heading and a centred column; returns the page and the column."""
    outer = QScrollArea()
    outer.setWidgetResizable(True)
    outer.setFrameShape(QFrame.NoFrame)
    body = QWidget()
    body.setObjectName("Page")
    row = QHBoxLayout(body)
    row.setContentsMargins(40, 36, 40, 36)
    column = QWidget()
    column.setMaximumWidth(CONTENT_WIDTH)
    lay = QVBoxLayout(column)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(14)
    lay.addWidget(label(title, font=style.heading_font(20)))
    row.addStretch(1)
    row.addWidget(column, 100)
    row.addStretch(1)
    outer.setWidget(body)
    return outer, lay


def setting_row(title: str, description: str | QLabel, right: QWidget) -> QWidget:
    """A title and description on the left, a control on the right. The description can be a
    label the caller keeps, to update it later."""
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 4, 0, 4)
    lay.setSpacing(16)
    text = QVBoxLayout()
    text.setSpacing(2)
    text.addWidget(label(title))
    text.addWidget(description if isinstance(description, QLabel) else label(description, "Dim", wrap=True))
    lay.addLayout(text, 1)
    lay.addWidget(right, 0, Qt.AlignVCenter)
    return w

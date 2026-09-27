"""Settings: the push-to-talk shortcut."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from .. import hotkey as hk
from . import style
from .widgets import Chips, card, divider, label, page, setting_row

DEFAULT = ["rctrl"]


class SettingsPage(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        outer, lay = page("Settings")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(outer)

        lay.addWidget(label("GENERAL", "Group"))
        frame, box = card(spacing=10)

        right = QWidget()
        r = QHBoxLayout(right)
        r.setContentsMargins(0, 0, 0, 0)
        r.setSpacing(10)
        self.chips = Chips(app.hotkey)
        self.prompt = label("Press your new shortcut…", "Accent")
        self.prompt.setVisible(False)
        self.change = QPushButton("Change")
        self.change.setObjectName("Secondary")
        self.change.setCursor(Qt.PointingHandCursor)
        self.change.clicked.connect(self._toggle_recording)
        r.addWidget(self.chips)
        r.addWidget(self.prompt)
        r.addWidget(self.change)
        box.addWidget(setting_row(
            "Push-to-talk shortcut",
            "Hold it to dictate, double-tap it for hands-free. Esc cancels.",
            right,
        ))

        self.error = label("", "Error", wrap=True)
        self.error.setVisible(False)
        box.addWidget(self.error)

        box.addWidget(divider())
        tip = QHBoxLayout()
        tip.addWidget(label("Pick a key you don't type with, like Right Ctrl, Right Alt or F9, "
                            "or a combo such as Ctrl + Shift + Space.", "Faint", wrap=True), 1)
        self.reset = QPushButton("Reset to Right Ctrl")
        self.reset.setObjectName("Link")
        self.reset.setCursor(Qt.PointingHandCursor)
        self.reset.clicked.connect(lambda: self._apply(DEFAULT))
        tip.addWidget(self.reset, 0, Qt.AlignTop)
        box.addLayout(tip)
        lay.addWidget(frame)
        lay.addStretch(1)

        self.recording = False
        app.hotkey_recorded.connect(self._recorded)
        self._sync()

    def _sync(self):
        self.chips.set(self.app.hotkey)
        self.chips.setVisible(not self.recording)
        self.prompt.setVisible(self.recording)
        self.change.setText("Cancel" if self.recording else "Change")
        self.reset.setVisible(self.app.hotkey != DEFAULT and not self.recording)

    def _toggle_recording(self):
        if self.recording:
            self.stop_recording()
            return
        self.error.setVisible(False)
        self.recording = True
        self.app.record_hotkey()
        self._sync()

    def stop_recording(self):
        if self.recording:
            self.recording = False
            self.app.cancel_hotkey_recording()
            self._sync()

    def _recorded(self, vks):
        if not self.recording:
            return
        self.recording = False
        if vks:
            names = hk.from_pressed(vks)
            reason = hk.problem(names)
            if reason:
                self.error.setText(f"{hk.describe(names)}: {reason}")
                self.error.setVisible(True)
            else:
                self._apply(names)
        self._sync()

    def _apply(self, names: list[str]):
        self.error.setVisible(False)
        self.app.set_hotkey(names)
        self._sync()

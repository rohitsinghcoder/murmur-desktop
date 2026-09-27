"""About: the model, a speed test, where your data lives, and the source code."""
import os

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget

from .. import history
from .widgets import card, divider, label, page, setting_row

VERSION = "0.2.0"
REPO = "https://github.com/rohitsinghcoder/murmur-desktop"


def _button(text: str, primary=False) -> QPushButton:
    b = QPushButton(text)
    b.setObjectName("Primary" if primary else "Secondary")
    b.setCursor(Qt.PointingHandCursor)
    return b


class AboutPage(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        outer, lay = page("About")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(outer)

        lay.addWidget(label(f"Murmur Desktop {VERSION}. Private voice typing: speech recognition "
                            "runs entirely on this computer, and nothing you say leaves it.", "Dim", wrap=True))

        lay.addWidget(label("SPEECH MODEL", "Group"))
        frame, box = card(spacing=10)
        box.addWidget(label("NVIDIA Nemotron Speech Streaming 0.6B (int8), running on your CPU "
                            "through sherpa-onnx."))
        self.model_info = label("", "Dim", wrap=True)
        box.addWidget(self.model_info)
        box.addWidget(divider())
        self.speed_button = _button("Run")
        self.speed_button.clicked.connect(self._speed_test)
        self.speed_result = label("How fast the model runs on this computer.", "Dim", wrap=True)
        box.addWidget(setting_row("Speed test", self.speed_result, self.speed_button))
        lay.addWidget(frame)

        lay.addWidget(label("YOUR DATA", "Group"))
        frame, box = card(spacing=10)
        folder = _button("Open folder")
        folder.clicked.connect(self._open_folder)
        box.addWidget(setting_row("History and settings",
                                  f"Stored only on this PC, in {history.DIR}.", folder))
        lay.addWidget(frame)

        lay.addWidget(label("SOURCE CODE", "Group"))
        frame, box = card(spacing=10)
        github = _button("Open on GitHub")
        github.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(REPO)))
        box.addWidget(setting_row("murmur-desktop",
                                  "Open source. The Android version lives at rohitsinghcoder/Murmur.", github))
        lay.addWidget(frame)
        lay.addStretch(1)

        app.speed_result.connect(self._speed_done)
        app.status_changed.connect(self.refresh)

    def refresh(self):
        parts = []
        if self.app.load_secs:
            parts.append(f"Loaded in {self.app.load_secs:.1f} s.")
        if self.app.last_latency_ms is not None:
            parts.append(f"Your last dictation was ready {self.app.last_latency_ms} ms after you let go.")
        self.model_info.setText(" ".join(parts) or "Loading…")
        self.speed_button.setEnabled(self.app.status == "ready")

    def _speed_test(self):
        self.speed_button.setEnabled(False)
        self.speed_result.setText("Running…")
        self.app.run_speed_test()

    def _speed_done(self, text: str):
        self.speed_result.setText(text)
        self.speed_button.setEnabled(True)

    def _open_folder(self):
        history.DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(history.DIR)

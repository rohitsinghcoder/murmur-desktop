"""The listening pill: a small bar at the bottom of the screen with a level meter and live text.

It never takes focus and ignores the mouse, so the app you are typing into keeps its cursor.
"""
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QFont, QFontMetrics, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

HEIGHT = 44
MIN_W, MAX_W = 150, 620
BARS = 12
PAD = 16

BG = QColor(22, 22, 27, 240)
BORDER = QColor(255, 255, 255, 34)
TEXT = QColor(240, 240, 245)
DIM = QColor(150, 150, 160)
ACCENT = QColor(124, 156, 255)
DONE = QColor(88, 204, 130)
ERROR = QColor(255, 120, 110)


class Overlay(QWidget):
    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
            | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.font = QFont("Segoe UI", 10)
        self.small = QFont("Segoe UI", 8, QFont.DemiBold)
        self.mode = "idle"  # idle | loading | listening | finishing | done | message
        self.text = ""
        self.levels: list[float] = []
        self.hands_free = False
        self.message_color = DIM
        self._hide_timer = QTimer(self, singleShot=True, timeout=self._hide)

    # State changes (main thread only).

    def listening(self):
        self._hide_timer.stop()
        self.mode, self.text, self.levels, self.hands_free = "listening", "", [], False
        self._show()

    def locked(self):
        self.hands_free = True
        self.update()

    def partial(self, text: str):
        if self.mode == "listening":
            self.text = text
            self._show()

    def set_levels(self, levels: list[float]):
        if self.mode == "listening":
            self.levels = levels
            self.update()

    def finishing(self):
        if self.mode == "listening":
            self.mode = "finishing"
            self.update()

    def done(self):
        self.mode, self.text = "done", ""
        self._show()
        self._hide_timer.start(700)

    def show_message(self, text: str, error=False, ms=2500):
        self.mode, self.text = "message", text
        self.message_color = ERROR if error else TEXT
        self._show()
        if ms:
            self._hide_timer.start(ms)

    def hide_now(self):
        self._hide()

    def _hide(self):
        self.mode = "idle"
        self.hide()

    # Layout and painting.

    def _label(self) -> tuple[str, QColor]:
        if self.mode == "listening":
            return (self.text, TEXT) if self.text else ("Listening…", DIM)
        if self.mode == "finishing":
            return (self.text or "…", DIM)
        if self.mode == "message":
            return self.text, self.message_color
        return "", TEXT

    def _left_width(self) -> int:
        if self.mode in ("listening", "finishing"):
            return BARS * 5 + 12
        if self.mode == "done":
            return 20
        return 0

    def _show(self):
        text, _ = self._label()
        fm = QFontMetrics(self.font)
        tag = 64 if self.hands_free and self.mode == "listening" else 0
        w = PAD * 2 + self._left_width() + (fm.horizontalAdvance(text) + 2 if text else 0) + tag
        w = max(MIN_W if self.mode != "done" else HEIGHT, min(MAX_W, w))
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        self.setGeometry(area.x() + (area.width() - w) // 2, area.bottom() - HEIGHT - 28, w, HEIGHT)
        if not self.isVisible():
            self.show()
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(r, r.height() / 2, r.height() / 2)
        p.fillPath(path, BG)
        p.setPen(QPen(BORDER, 1))
        p.drawPath(path)

        x = PAD
        mid = self.height() / 2
        if self.mode == "done":
            p.setPen(QPen(DONE, 2.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            cx = self.width() / 2
            p.drawPolyline([QPointF(cx - 7, mid), QPointF(cx - 2, mid + 5), QPointF(cx + 7, mid - 5)])
            return
        if self.mode in ("listening", "finishing"):
            levels = ([0.0] * BARS + self.levels)[-BARS:]
            color = ACCENT if self.mode == "listening" else DIM
            for i, lv in enumerate(levels):
                h = 4 + lv * 18
                p.fillRect(QRectF(x + i * 5, mid - h / 2, 3, h), color)
            x += BARS * 5 + 12

        text, color = self._label()
        right = self.width() - PAD
        if self.hands_free and self.mode == "listening":
            p.setFont(self.small)
            p.setPen(ACCENT)
            p.drawText(QRectF(right - 60, 0, 60, self.height()), Qt.AlignVCenter | Qt.AlignRight, "HANDS-FREE")
            right -= 64
        p.setFont(self.font)
        p.setPen(color)
        # Show the end of long text: that's where the new words are.
        shown = QFontMetrics(self.font).elidedText(text, Qt.ElideLeft, int(right - x))
        p.drawText(QRectF(x, 0, right - x, self.height()), Qt.AlignVCenter | Qt.AlignLeft, shown)

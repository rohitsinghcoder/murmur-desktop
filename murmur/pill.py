"""The Murmur bar: a small floating bubble at the bottom of the screen.

- Resting: a tiny bar. Hover it for a hint; click it to dictate hands-free.
- Recording: a black pill with white bars that move with your voice.
- Hands-free: the same, with ✕ (cancel) and ■ (stop) buttons.
- Processing: the bars turn into a travelling shimmer, then it shrinks back to resting.

Sizes spring between states. The bar never takes focus, so the app you're typing into keeps
its cursor, and clicks outside the pill go through to whatever is underneath.
"""
import math
import random
import time

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QCursor, QFont, QFontMetricsF, QGuiApplication, QPainter,
                           QPainterPath, QPen, QRegion)
from PySide6.QtWidgets import QWidget

WIN_W, WIN_H = 420, 64
BOTTOM_GAP = 10  # between the pill and the taskbar
BARS = 9
BAR_W, BAR_GAP = 3.0, 3.0
BAR_MIN, BAR_MAX = 3.0, 18.0
# Taller bars in the middle, like a voice waveform.
PROFILE = [0.45, 0.62, 0.8, 0.94, 1.0, 0.94, 0.8, 0.62, 0.45]

BG = QColor(8, 8, 10, 242)
BORDER = QColor(255, 255, 255, 40)
REST_BG = QColor(20, 20, 24, 200)
REST_BORDER = QColor(255, 255, 255, 70)
WHITE = QColor(255, 255, 255)
HINT = QColor(228, 228, 232)
ERROR = QColor(255, 138, 128)
BUTTON = QColor(44, 44, 50)
STOP = QColor(239, 68, 68)

SIZES = {
    "rest": (44.0, 8.0),
    "record": (100.0, 34.0),
    "handsfree": (156.0, 34.0),
    "process": (100.0, 34.0),
}


class Spring:
    """A value that springs toward a target with a little overshoot."""

    def __init__(self, value: float):
        self.value = self.target = value
        self.velocity = 0.0

    def step(self, dt: float, stiffness=420.0, damping=30.0):
        accel = stiffness * (self.target - self.value) - damping * self.velocity
        self.velocity += accel * dt
        self.value += self.velocity * dt

    @property
    def settled(self) -> bool:
        return abs(self.target - self.value) < 0.05 and abs(self.velocity) < 0.05


class Pill(QWidget):
    start_clicked = Signal()
    cancel_clicked = Signal()
    stop_clicked = Signal()

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.resize(WIN_W, WIN_H)
        self.hint_font = QFont("Geist", 9, QFont.Medium)

        self.state = "rest"
        self.loading = True
        self.hover = False
        self.hint = "Loading speech model…"
        self.message = ""
        self.message_error = False
        self.level = 0.0  # latest mic level, 0..1
        self.smooth_level = 0.0
        self.w, self.h = Spring(SIZES["rest"][0]), Spring(SIZES["rest"][1])
        self.bars = [BAR_MIN] * BARS
        self.phases = [random.uniform(0, math.tau) for _ in range(BARS)]
        self.speeds = [random.uniform(5.0, 9.0) for _ in range(BARS)]
        self.t = 0.0
        self._last = time.perf_counter()
        self._mask = QRect()

        self.timer = QTimer(self, interval=16, timeout=self._tick)
        self._message_timer = QTimer(self, singleShot=True, timeout=self._end_message)

    # State changes (UI thread only).

    def ready(self, hint: str):
        self.loading = False
        self.hint = hint
        self._retarget()

    def set_hint(self, hint: str):
        self.hint = hint
        self._retarget()

    def recording(self, hands_free=False):
        self._message_timer.stop()
        self.state = "handsfree" if hands_free else "record"
        self.hover = False
        self.level = self.smooth_level = 0.0
        self._move_to_cursor_screen()
        self._retarget()

    def hands_free(self):
        if self.state == "record":
            self.state = "handsfree"
            self._retarget()

    def set_level(self, levels: list[float]):
        if levels:
            # Mic levels are squared for the meter; the square root reads better as bar height.
            self.level = math.sqrt(levels[-1])

    def processing(self):
        if self.state in ("record", "handsfree"):
            self.state = "process"
            self._retarget()

    def rest(self):
        self.state = "rest"
        self._retarget()

    def show_message(self, text: str, error=False, ms=2600):
        self.state = "message"
        self.message, self.message_error = text, error
        self._move_to_cursor_screen()
        self._retarget()
        self._message_timer.start(ms)

    def _end_message(self):
        if self.state == "message":
            self.rest()

    # Geometry.

    def _text_size(self, text: str) -> tuple[float, float]:
        return QFontMetricsF(self.hint_font).horizontalAdvance(text) + 30, 30.0

    def _target(self) -> tuple[float, float]:
        if self.state == "message":
            return min(self._text_size(self.message)[0], WIN_W - 8), 32.0
        if self.state == "rest" and self.hover:
            return self._text_size(self.hint)
        return SIZES[self.state]

    def _retarget(self):
        self.w.target, self.h.target = self._target()
        if not self.isVisible():
            self._move_to_cursor_screen()
            self.show()
        self._last = time.perf_counter()
        if not self.timer.isActive():
            self.timer.start()

    def _move_to_cursor_screen(self):
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        self.move(area.x() + (area.width() - WIN_W) // 2, area.bottom() - WIN_H - BOTTOM_GAP + 1)

    def _pill_rect(self) -> QRectF:
        w, h = max(self.w.value, 6.0), max(self.h.value, 4.0)
        return QRectF((WIN_W - w) / 2, WIN_H - 8 - h, w, h)

    def _update_mask(self):
        # Only the pill (plus some slack so the thin resting bar is easy to hover) takes the mouse.
        r = self._pill_rect().adjusted(-10, -10, 10, 6).toAlignedRect() & self.rect()
        if r != self._mask:
            self._mask = r
            self.setMask(QRegion(r))

    # Animation.

    def _tick(self):
        now = time.perf_counter()
        dt = min(now - self._last, 0.05)
        self._last = now
        self.t += dt
        self.w.step(dt)
        self.h.step(dt)

        # Fast attack, slower release, like a VU meter.
        rate = 30.0 if self.level > self.smooth_level else 9.0
        self.smooth_level += (self.level - self.smooth_level) * (1 - math.exp(-rate * dt))
        for i in range(BARS):
            if self.state in ("record", "handsfree"):
                wobble = 0.72 + 0.28 * math.sin(self.t * self.speeds[i] + self.phases[i])
                target = BAR_MIN + (BAR_MAX - BAR_MIN) * min(1.0, self.smooth_level * PROFILE[i] * wobble * 1.25)
            else:
                target = BAR_MIN
            self.bars[i] += (target - self.bars[i]) * (1 - math.exp(-22 * dt))

        self._update_mask()
        self.update()
        idle = self.state == "rest" and not self.hover and not self.loading
        if idle and self.w.settled and self.h.settled:
            self.timer.stop()

    # Input.

    def _buttons(self) -> tuple[QPointF, QPointF]:
        r = self._pill_rect()
        cy = r.center().y()
        return QPointF(r.left() + 17, cy), QPointF(r.right() - 17, cy)

    def enterEvent(self, event):
        if self.state == "rest":
            self.hover = True
            self._retarget()

    def leaveEvent(self, event):
        if self.hover:
            self.hover = False
            self._retarget()
        self.unsetCursor()

    def mouseMoveEvent(self, event):
        pos = event.position()
        clickable = (self.state == "rest" and not self.loading) or (
            self.state == "handsfree" and any(_near(pos, b) for b in self._buttons())
        )
        self.setCursor(Qt.PointingHandCursor if clickable else Qt.ArrowCursor)

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        if self.state == "rest" and not self.loading:
            self.hover = False
            self.start_clicked.emit()
        elif self.state == "handsfree":
            cancel, stop = self._buttons()
            if _near(event.position(), cancel):
                self.cancel_clicked.emit()
            elif _near(event.position(), stop):
                self.stop_clicked.emit()

    # Painting.

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        # Nearly invisible, but makes the slack around the resting bar hoverable.
        p.fillRect(QRectF(self._mask), QColor(0, 0, 0, 1))

        r = self._pill_rect()
        path = QPainterPath()
        path.addRoundedRect(r, r.height() / 2, r.height() / 2)
        resting = self.state == "rest" and not self.hover
        if resting and self.loading:
            pulse = 0.55 + 0.45 * (0.5 + 0.5 * math.sin(self.t * 4))
            p.setOpacity(pulse)
        p.fillPath(path, REST_BG if resting else BG)
        p.setPen(QPen(REST_BORDER if resting else BORDER, 1))
        p.drawPath(path)
        p.setOpacity(1.0)

        tw, _ = self._target()
        # Content fades in as the pill reaches its size, so nothing spills while it grows.
        alpha = max(0.0, min(1.0, (r.width() / tw - 0.75) / 0.25)) if tw else 0.0
        if alpha <= 0 or resting:
            return
        p.setClipPath(path)
        p.setOpacity(alpha)
        cx, cy = r.center().x(), r.center().y()

        if self.state == "rest" or self.state == "message":
            text = self.hint if self.state == "rest" else self.message
            p.setFont(self.hint_font)
            p.setPen(ERROR if self.state == "message" and self.message_error else HINT)
            p.drawText(r, Qt.AlignCenter, text)
            return

        if self.state == "handsfree":
            cancel, stop = self._buttons()
            p.setPen(Qt.NoPen)
            p.setBrush(BUTTON)
            p.drawEllipse(cancel, 11, 11)
            p.setPen(QPen(WHITE, 1.6, Qt.SolidLine, Qt.RoundCap))
            d = 3.6
            p.drawLine(cancel + QPointF(-d, -d), cancel + QPointF(d, d))
            p.drawLine(cancel + QPointF(-d, d), cancel + QPointF(d, -d))
            p.setPen(Qt.NoPen)
            p.setBrush(STOP)
            p.drawEllipse(stop, 11, 11)
            p.setBrush(WHITE)
            p.drawRoundedRect(QRectF(stop.x() - 3.5, stop.y() - 3.5, 7, 7), 1.5, 1.5)

        total = BARS * BAR_W + (BARS - 1) * BAR_GAP
        x0 = cx - total / 2
        p.setPen(Qt.NoPen)
        for i in range(BARS):
            if self.state == "process":
                # A shimmer travelling across the dots.
                wave = max(0.0, math.sin(self.t * 7 - i * 0.7)) ** 2
                h = BAR_MIN + 5 * wave
                c = QColor(WHITE)
                c.setAlphaF(0.45 + 0.55 * wave)
            else:
                h = self.bars[i]
                c = WHITE
            p.setBrush(c)
            p.drawRoundedRect(QRectF(x0 + i * (BAR_W + BAR_GAP), cy - h / 2, BAR_W, h), BAR_W / 2, BAR_W / 2)


def _near(pos: QPointF, center: QPointF, radius=13.0) -> bool:
    return (pos.x() - center.x()) ** 2 + (pos.y() - center.y()) ** 2 <= radius * radius

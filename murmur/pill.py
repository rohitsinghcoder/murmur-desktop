"""The Murmur bar: a small floating bubble at the bottom of the screen.

- Resting: a tiny bar. Hover it for a hint; click it to dictate hands-free.
- Recording: a black pill with white bars that move with your voice.
- Hands-free: the same, with ✕ (cancel) and ■ (stop) buttons and how long it's been going.
- Processing: the bars turn into a travelling shimmer; once the text is in, a brief check mark,
  then it shrinks back to resting.
- Paused: the resting bar is dimmed; clicking it resumes.
- Hidden at rest when turned off in Settings, and while a fullscreen window (a video, a game,
  a slideshow) is in front of it (`set_covered`); it still appears while dictating.
- Messages: a line of text, with an accent action ("Undo") when clicking it does something.

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
BAR_MIN, BAR_MAX = 3.0, 22.0
BARS_W = BARS * BAR_W + (BARS - 1) * BAR_GAP
CLOCK_GAP = 10  # between the bars and the hands-free clock
# Taller bars in the middle, like a voice waveform.
PROFILE = [0.5, 0.66, 0.82, 0.95, 1.0, 0.95, 0.82, 0.66, 0.5]
# Automatic gain: bars are scaled to the loudest recent speech, so a quiet mic still moves them,
# but never by more than this much (room noise must stay flat).
GAIN_FLOOR = 0.35
# Levels below this (about -47 dB: fans, keyboard) leave the bars flat.
GATE = 0.1
# Each bar gets a new random share of the level this often, so they move independently.
JITTER_S = 0.09

BG = QColor(8, 8, 10, 242)
BORDER = QColor(255, 255, 255, 40)
REST_BG = QColor(20, 20, 24, 200)
REST_BORDER = QColor(255, 255, 255, 70)
WHITE = QColor(255, 255, 255)
HINT = QColor(228, 228, 232)
ERROR = QColor(255, 138, 128)
DIM = QColor(150, 150, 158)
BUTTON = QColor(44, 44, 50)
BUTTON_HOVER = QColor(62, 62, 70)
# The same red as the bar drawn in Settings (.pp-stop in web/style.css).
STOP = QColor(229, 72, 77)
STOP_HOVER = QColor(236, 102, 106)
ACCENT = QColor(240, 147, 107)  # web/style.css --toast-accent: the accent, light enough on black
MESSAGE_HOVER = QColor(30, 30, 35, 245)
PAUSED_OPACITY = 0.4

SIZES = {
    "rest": (44.0, 8.0),
    "record": (100.0, 34.0),
    "handsfree": (196.0, 34.0),
    "process": (100.0, 34.0),
    "done": (56.0, 34.0),
}
# The check mark after inserting: drawn on over TICK_DRAW_S, then the bar rests after TICK_MS.
TICK_DRAW_S = 0.22
TICK_MS = 750
MESSAGE_PAD = 30  # around a message's text
ACTION_GAP = 12  # between a message and its action


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
        self.action_font = QFont("Geist", 9, QFont.DemiBold)
        self.timer_font = QFont("Geist Mono", 8, QFont.Medium)

        self.state = "rest"
        self.loading = True
        self.show_idle = True  # False (Settings): no resting bar, only the pill while in use
        self.covered = False  # a fullscreen window (a video, a game) is in front: no resting bar
        self.paused = False
        self.hover = False
        self.hover_button = None  # "cancel" or "stop" while hands-free
        self.hover_message = False
        self.hint = "Loading speech model…"
        self.message = ""
        self.message_error = False
        self.message_action = None  # what clicking the message does
        self.action_label = ""  # and what it says it does, in the accent
        self.recording_since = 0.0  # perf_counter, for the hands-free clock
        self.level = 0.0  # latest mic level, 0..1
        self.smooth_level = 0.0
        self.w, self.h = Spring(SIZES["rest"][0]), Spring(SIZES["rest"][1])
        self.bars = [BAR_MIN] * BARS
        self.peak = GAIN_FLOOR
        self.jitter = [1.0] * BARS
        self.next_jitter = 0.0
        self.t = 0.0
        self.done_at = 0.0
        self._last = time.perf_counter()
        self._mask = QRect()

        self.timer = QTimer(self, interval=16, timeout=self._tick)
        self._message_timer = QTimer(self, singleShot=True, timeout=self._end_message)
        # Placed before it is ever shown; otherwise Windows puts a new window mid-screen.
        self._move_to_cursor_screen()
        # And again when the taskbar moves or the resolution or scaling changes.
        for screen in QGuiApplication.screens():
            screen.availableGeometryChanged.connect(lambda _: self._move_to_cursor_screen())
        QGuiApplication.instance().screenAdded.connect(lambda _: self._move_to_cursor_screen())
        QGuiApplication.instance().screenRemoved.connect(lambda _: self._move_to_cursor_screen())

    # State changes (UI thread only).

    def ready(self, hint: str):
        self.loading = False
        self.hint = hint
        self._retarget()

    def set_hint(self, hint: str):
        self.hint = hint
        self._retarget()

    def set_paused(self, paused: bool, hint: str):
        self.paused = paused
        self.hint = hint
        self._retarget()

    def set_show_idle(self, on: bool):
        self.show_idle = on
        self._retarget()

    def set_covered(self, covered: bool):
        if covered != self.covered:
            self.covered = covered
            self._retarget()

    @property
    def idle_shown(self) -> bool:
        """Whether the resting bar is shown (the pill always is while in use)."""
        return self.show_idle and not self.covered

    def recording(self, hands_free=False):
        self._message_timer.stop()
        self.state = "handsfree" if hands_free else "record"
        self.hover = self.hover_message = False
        self.recording_since = time.perf_counter()
        self.level = self.smooth_level = 0.0
        self.peak = GAIN_FLOOR
        self._move_to_cursor_screen()
        self._retarget()

    def hands_free(self):
        if self.state == "record":
            self.state = "handsfree"
            self._retarget()

    def set_level(self, levels: list[float]):
        if levels:
            self.level = levels[-1]

    def processing(self):
        if self.state in ("record", "handsfree"):
            self.state = "process"
            self._retarget()

    def rest(self):
        self.state = "rest"
        self._move_to_cursor_screen()
        self._retarget()

    def done(self):
        """A brief check mark once the text is in, then back to resting."""
        self.state = "done"
        self.done_at = self.t
        self._retarget()
        self._message_timer.start(TICK_MS)

    def show_message(self, text: str, error=False, ms=2600, action="", on_click=None):
        """A short message in the pill. With `on_click`, clicking it does that and dismisses it;
        `action` names that ("Undo") and is drawn after the text, in the accent."""
        self.state = "message"
        self.message, self.message_error = text, error
        self.message_action = on_click
        self.action_label = action if on_click else ""
        self.hover_message = False
        self._move_to_cursor_screen()
        self._retarget()
        self._message_timer.start(ms)

    def _end_message(self):
        if self.state in ("message", "done"):
            self.rest()

    # Geometry.

    def _text_size(self, text: str) -> tuple[float, float]:
        return QFontMetricsF(self.hint_font).horizontalAdvance(text) + MESSAGE_PAD, 30.0

    def _message_layout(self) -> tuple[str, float, float]:
        """The message as it fits (cut short with … if it must), its width and its action's."""
        action_w = QFontMetricsF(self.action_font).horizontalAdvance(self.action_label) if self.action_label else 0.0
        room = WIN_W - 8 - MESSAGE_PAD - (action_w + ACTION_GAP if action_w else 0)
        metrics = QFontMetricsF(self.hint_font)
        text = metrics.elidedText(self.message, Qt.ElideRight, room)
        return text, metrics.horizontalAdvance(text), action_w

    def _target(self) -> tuple[float, float]:
        if self.state == "message":
            _, text_w, action_w = self._message_layout()
            return text_w + (action_w + ACTION_GAP if action_w else 0) + MESSAGE_PAD, 32.0
        if self.state == "rest" and self.hover:
            return self._text_size(self.hint)
        return SIZES[self.state]

    def _retarget(self):
        self.w.target, self.h.target = self._target()
        if not self.isVisible() and (self.idle_shown or self.state != "rest"):
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
        rate = 35.0 if self.level > self.smooth_level else 10.0
        self.smooth_level += (self.level - self.smooth_level) * (1 - math.exp(-rate * dt))
        # The gain follows the loudest recent speech: up at once, back down over a few seconds.
        self.peak = max(self.smooth_level, GAIN_FLOOR + (self.peak - GAIN_FLOOR) * math.exp(-0.4 * dt))
        loudness = min(1.0, max(0.0, self.smooth_level - GATE) / (self.peak - GATE))
        if self.t >= self.next_jitter:
            self.next_jitter = self.t + JITTER_S
            self.jitter = [random.uniform(0.45, 1.0) for _ in range(BARS)]
        for i in range(BARS):
            if self.state in ("record", "handsfree"):
                target = BAR_MIN + (BAR_MAX - BAR_MIN) * loudness * PROFILE[i] * self.jitter[i]
            else:
                target = BAR_MIN
            # Bars jump up quickly and settle back more slowly.
            speed = 26.0 if target > self.bars[i] else 12.0
            self.bars[i] += (target - self.bars[i]) * (1 - math.exp(-speed * dt))

        self._update_mask()
        self.update()
        idle = self.state == "rest" and not self.hover and not self.loading
        if idle and self.w.settled and self.h.settled:
            self.timer.stop()
            if not self.idle_shown:
                self.hide()

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
        self._set_hovers(None, False)
        self.unsetCursor()

    def _set_hovers(self, button, message: bool):
        if (button, message) != (self.hover_button, self.hover_message):
            self.hover_button, self.hover_message = button, message
            self.update()

    def mouseMoveEvent(self, event):
        pos = event.position()
        button = None
        if self.state == "handsfree":
            cancel, stop = self._buttons()
            button = "cancel" if _near(pos, cancel) else "stop" if _near(pos, stop) else None
        message = self.state == "message" and self.message_action is not None and self._pill_rect().contains(pos)
        self._set_hovers(button, message)
        clickable = (self.state == "rest" and not self.loading) or button is not None or message
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
        elif self.state == "message" and self.message_action and self._pill_rect().contains(event.position()):
            action = self.message_action
            self.rest()
            action()

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
        elif resting and self.paused:
            p.setOpacity(PAUSED_OPACITY)
        elif resting and not self.idle_shown:
            # Hidden when idle: fades out as it shrinks back, then the window hides.
            rest_w, record_w = SIZES["rest"][0], SIZES["record"][0]
            p.setOpacity(max(0.0, min(1.0, (r.width() - rest_w) / (record_w - rest_w))))
        hovered = self.state == "message" and self.hover_message
        p.fillPath(path, REST_BG if resting else MESSAGE_HOVER if hovered else BG)
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

        if self.state == "rest":
            p.setFont(self.hint_font)
            p.setPen(HINT)
            p.drawText(r, Qt.AlignCenter, self.hint)
            return

        if self.state == "message":
            text, text_w, action_w = self._message_layout()
            x = cx - (text_w + (action_w + ACTION_GAP if action_w else 0)) / 2
            p.setFont(self.hint_font)
            p.setPen(ERROR if self.message_error else HINT)
            p.drawText(QRectF(x, r.top(), text_w + 1, r.height()), Qt.AlignLeft | Qt.AlignVCenter, text)
            if action_w:
                p.setFont(self.action_font)
                p.setPen(WHITE if self.message_error else ACCENT)  # the accent is too near the red
                p.drawText(QRectF(x + text_w + ACTION_GAP, r.top(), action_w + 1, r.height()),
                           Qt.AlignLeft | Qt.AlignVCenter, self.action_label)
            return

        if self.state == "done":
            # A check mark drawn on like a pen stroke, easing out.
            k = min(1.0, (self.t - self.done_at) / TICK_DRAW_S)
            k = 1 - (1 - k) ** 3
            pts = [QPointF(cx - 6.5, cy + 0.5), QPointF(cx - 2, cy + 5), QPointF(cx + 7, cy - 5)]
            legs = [math.dist(a.toTuple(), b.toTuple()) for a, b in zip(pts, pts[1:])]
            left = k * sum(legs)
            tick = QPainterPath(pts[0])
            for a, b, leg in zip(pts, pts[1:], legs):
                f = min(1.0, left / leg)
                tick.lineTo(a + (b - a) * f)
                left -= leg
                if left <= 0:
                    break
            p.setPen(QPen(WHITE, 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(Qt.NoBrush)
            p.drawPath(tick)
            return

        x0 = cx - BARS_W / 2
        if self.state == "handsfree":
            cancel, stop = self._buttons()
            p.setPen(Qt.NoPen)
            p.setBrush(BUTTON_HOVER if self.hover_button == "cancel" else BUTTON)
            p.drawEllipse(cancel, 11, 11)
            p.setPen(QPen(WHITE, 1.6, Qt.SolidLine, Qt.RoundCap))
            d = 3.6
            p.drawLine(cancel + QPointF(-d, -d), cancel + QPointF(d, d))
            p.drawLine(cancel + QPointF(-d, d), cancel + QPointF(d, -d))
            p.setPen(Qt.NoPen)
            p.setBrush(STOP_HOVER if self.hover_button == "stop" else STOP)
            p.drawEllipse(stop, 11, 11)
            p.setBrush(WHITE)
            p.drawRoundedRect(QRectF(stop.x() - 3.5, stop.y() - 3.5, 7, 7), 1.5, 1.5)
            # How long it's been going, after the bars; the two are centred together.
            secs = int(time.perf_counter() - self.recording_since)
            clock_w = QFontMetricsF(self.timer_font).horizontalAdvance("0:00")
            x0 = cx - (BARS_W + CLOCK_GAP + clock_w) / 2
            p.setFont(self.timer_font)
            p.setPen(DIM)
            p.drawText(QRectF(x0 + BARS_W + CLOCK_GAP, r.top(), clock_w + 12, r.height()),
                       Qt.AlignLeft | Qt.AlignVCenter, f"{secs // 60}:{secs % 60:02d}")

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

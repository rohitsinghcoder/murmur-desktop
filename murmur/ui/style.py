"""Murmur's logo, window frame and tray menu style. The window itself is HTML (ui/web)."""
import ctypes
import struct
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PySide6.QtGui import QColor, QFontDatabase, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap

# Window background per theme, matching --bg in web/style.css.
BG = {"dark": "#0d0d0f", "light": "#ffffff"}
FONTS = Path(__file__).resolve().parent / "web" / "fonts"

# The logo: five bars of a voice waveform, shaped like an M, on a charcoal tile. The middle bar
# is the accent, like a recording light. Same drawing as LOGO in web/app.js.
BAR_HEIGHTS = [0.30, 0.54, 0.34, 0.54, 0.30]
TILE = "#1d1d20"
BAR = "#ededee"
ACCENT = "#e07a50"
DIMMED = "#6f6f76"  # all bars while the model is loading


def logo_image(size: int, gray=False) -> QImage:
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    s = float(size)
    edge = max(1.0, s / 96)
    tile = QPainterPath()
    tile.addRoundedRect(QRectF(0, 0, s, s), s * 0.25, s * 0.25)
    p.fillPath(tile, QColor(TILE))
    rim = QPainterPath()
    rim.addRoundedRect(QRectF(edge / 2, edge / 2, s - edge, s - edge), s * 0.25 - edge / 2, s * 0.25 - edge / 2)
    p.setPen(QPen(QColor(255, 255, 255, 31), edge))
    p.drawPath(rim)

    w, gap = s * 0.095, s * 0.06
    x = (s - (5 * w + 4 * gap)) / 2
    p.setPen(Qt.NoPen)
    for i, h in enumerate(BAR_HEIGHTS):
        p.setBrush(QColor(DIMMED if gray else ACCENT if i == 2 else BAR))
        h *= s
        p.drawRoundedRect(QRectF(x + i * (w + gap), (s - h) / 2, w, h), w / 2, w / 2)
    p.end()
    return img


def load_fonts():
    """Registers the bundled Geist fonts with Qt (the web view loads its own copies)."""
    for name in ("Geist-Variable.ttf", "GeistMono-Variable.ttf"):
        QFontDatabase.addApplicationFont(str(FONTS / name))


def logo_icon(gray=False) -> QIcon:
    """The logo drawn separately at each size, so small ones (tray, title bar) stay crisp."""
    icon = QIcon()
    for size in (16, 20, 24, 32, 40, 48, 64, 128, 256):
        icon.addPixmap(QPixmap.fromImage(logo_image(size, gray)))
    return icon


def write_ico(path, sizes=(16, 20, 24, 32, 40, 48, 64, 128, 256)):
    """Writes the logo as a multi-size .ico (PNG-compressed entries), for shortcuts."""
    images = []
    for size in sizes:
        data = QByteArray()
        buf = QBuffer(data)
        buf.open(QIODevice.WriteOnly)
        logo_image(size).save(buf, "PNG")
        images.append((size, bytes(data)))
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, blobs = b"", b""
    for size, png in images:
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset)
        offset += len(png)
        blobs += png
    with open(path, "wb") as f:
        f.write(header + entries + blobs)


def system_theme() -> str:
    """Windows' app theme (Settings > Personalization > Colors)."""
    from PySide6.QtGui import QGuiApplication
    return "light" if QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Light else "dark"


def title_bar(widget, theme: str):
    """The window frame's dark or light mode on Windows 10/11 (its border and system menu). The
    title bar itself is drawn by the page (see frame.py)."""
    hwnd = int(widget.winId())
    dark = ctypes.c_int(theme == "dark")
    ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), ctypes.sizeof(dark))


# The tray menu, like the row menu in web/style.css.
_MENU = """
QMenu {{ background: {bg}; color: {text}; border: 1px solid {line}; border-radius: 8px; padding: 4px; }}
QMenu::item {{ padding: 7px 22px 7px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: {hover}; }}
QMenu::item:disabled {{ color: {dim}; }}
QMenu::separator {{ height: 1px; background: {line}; margin: 4px 8px; }}
"""
_MENU_COLORS = {
    "dark": {"bg": "#161618", "text": "#ededee", "line": "#27272b", "hover": "#222226", "dim": "#8e8e95"},
    "light": {"bg": "#ffffff", "text": "#18181b", "line": "#e4e4e7", "hover": "#f4f4f5", "dim": "#686870"},
}


def menu_stylesheet(theme: str) -> str:
    return _MENU.format(**_MENU_COLORS[theme])

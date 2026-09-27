"""Murmur's logo, window frame and tray menu style. The window itself is HTML (ui/web)."""
import ctypes
import struct
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PySide6.QtGui import QColor, QFontDatabase, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap

BG = "#0d0d0f"
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


def dark_title_bar(widget):
    """Dark window frame on Windows 10/11, blended with the window background."""
    hwnd = int(widget.winId())
    dwm = ctypes.windll.dwmapi
    on = ctypes.c_int(1)
    dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(on), ctypes.sizeof(on))  # immersive dark mode
    color = QColor(BG)
    colorref = ctypes.c_int(color.red() | color.green() << 8 | color.blue() << 16)
    dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(colorref), ctypes.sizeof(colorref))  # caption (Win 11)


MENU_STYLESHEET = """
QMenu { background: #161618; color: #ededee; border: 1px solid #27272b; border-radius: 8px; padding: 4px; }
QMenu::item { padding: 7px 22px 7px 12px; border-radius: 6px; }
QMenu::item:selected { background: #222226; }
QMenu::item:disabled { color: #8e8e95; }
QMenu::separator { height: 1px; background: #27272b; margin: 4px 8px; }
"""

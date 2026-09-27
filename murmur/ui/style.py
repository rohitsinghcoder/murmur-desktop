"""Colours, fonts, icons and the stylesheet for Murmur's window. Always dark."""
import ctypes

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPainterPath, QPen, QPixmap

BG = "#0e0e10"
SIDEBAR = "#09090b"
CARD = "#151518"
CARD_HOVER = "#1b1b1f"
BORDER = "#232328"
TEXT = "#ececef"
DIM = "#8e8e97"
FAINT = "#5d5d66"
ACCENT = "#a996ff"
DANGER = "#f87171"
GOOD = "#4ade80"

# Windows' own icon font: Segoe Fluent Icons on Windows 11, Segoe MDL2 Assets on Windows 10.
ICONS = {
    "home": "", "settings": "", "info": "", "copy": "", "check": "",
    "delete": "", "search": "", "mic": "", "folder": "", "link": "",
    "speed": "", "keyboard": "", "lock": "",
}


def icon_font(size: int = 11) -> QFont:
    families = QFontDatabase.families()
    family = "Segoe Fluent Icons" if "Segoe Fluent Icons" in families else "Segoe MDL2 Assets"
    f = QFont(family)
    f.setPointSize(size)
    return f


def heading_font(size: int) -> QFont:
    families = QFontDatabase.families()
    f = QFont("Segoe UI Variable Display" if "Segoe UI Variable Display" in families else "Segoe UI")
    f.setPointSize(size)
    f.setWeight(QFont.DemiBold)
    return f


def mic_icon(color: QColor, background: QColor | None = None) -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    if background:
        bg = QPainterPath()
        bg.addRoundedRect(0, 0, 64, 64, 16, 16)
        p.fillPath(bg, background)
        p.translate(8, 8)
        p.scale(0.75, 0.75)
    body = QPainterPath()
    body.addRoundedRect(22, 6, 20, 34, 10, 10)
    p.fillPath(body, color)
    p.setPen(QPen(color, 5, Qt.SolidLine, Qt.RoundCap))
    p.drawArc(13, 16, 38, 34, 180 * 16, 180 * 16)
    p.drawLine(32, 50, 32, 58)
    p.end()
    return QIcon(pm)


def dark_title_bar(widget):
    """Dark window frame on Windows 10/11, blended with the window background."""
    hwnd = int(widget.winId())
    dwm = ctypes.windll.dwmapi
    on = ctypes.c_int(1)
    dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(on), ctypes.sizeof(on))  # immersive dark mode
    color = QColor(BG)
    colorref = ctypes.c_int(color.red() | color.green() << 8 | color.blue() << 16)
    dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(colorref), ctypes.sizeof(colorref))  # caption (Win 11)


STYLESHEET = f"""
QWidget {{ color: {TEXT}; }}
#Root, #Page {{ background: {BG}; }}
#Sidebar {{ background: {SIDEBAR}; border-right: 1px solid {BORDER}; }}
QLabel {{ background: transparent; }}
QLabel#Dim {{ color: {DIM}; }}
QLabel#Faint {{ color: {FAINT}; }}
QLabel#Group {{ color: {FAINT}; font-size: 8pt; font-weight: 600; letter-spacing: 1px; }}
QLabel#Error {{ color: {DANGER}; }}
QLabel#Accent {{ color: {ACCENT}; }}
QLabel#StatValue {{ font-size: 17pt; font-weight: 600; }}
QLabel#Chip {{
    background: #232329; border: 1px solid #34343c; border-bottom: 2px solid #34343c;
    border-radius: 6px; padding: 2px 8px; font-weight: 600; font-size: 9pt;
}}

QPushButton#Nav {{
    text-align: left; padding: 8px 10px; border: none; border-radius: 8px; color: {DIM};
}}
QPushButton#Nav:hover {{ background: #141417; color: {TEXT}; }}
QPushButton#Nav:checked {{ background: #1a1a1f; color: {TEXT}; }}
QPushButton#Primary {{
    background: {TEXT}; color: {BG}; border: none; border-radius: 8px; padding: 7px 16px; font-weight: 600;
}}
QPushButton#Primary:hover {{ background: #ffffff; }}
QPushButton#Primary:disabled {{ background: #3a3a40; color: {DIM}; }}
QPushButton#Secondary {{
    background: #1c1c21; border: 1px solid {BORDER}; border-radius: 8px; padding: 7px 14px;
}}
QPushButton#Secondary:hover {{ background: #232329; }}
QPushButton#Link {{ background: transparent; border: none; color: {DIM}; padding: 0; }}
QPushButton#Link:hover {{ color: {TEXT}; }}
QToolButton#Icon {{
    background: transparent; border: none; border-radius: 6px; padding: 5px; color: {DIM};
}}
QToolButton#Icon:hover {{ background: #26262c; color: {TEXT}; }}

QFrame#Card {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 12px; }}
QFrame#Entry {{ background: transparent; border-radius: 8px; }}
QFrame#Entry:hover {{ background: {CARD_HOVER}; }}
QFrame#Divider {{ background: {BORDER}; max-height: 1px; min-height: 1px; border: none; }}

QLineEdit {{
    background: #121215; border: 1px solid {BORDER}; border-radius: 10px; padding: 9px 12px;
    selection-background-color: #4b3f8f;
}}
QLineEdit:focus {{ border: 1px solid #3b3b45; }}

QScrollArea {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #2a2a30; border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #3a3a42; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{
    height: 0; background: none;
}}

QMenu {{ background: #18181c; border: 1px solid {BORDER}; border-radius: 8px; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 5px; }}
QMenu::item:selected {{ background: #26262c; }}
QMenu::item:disabled {{ color: {DIM}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 6px; }}
QToolTip {{ background: #18181c; color: {TEXT}; border: 1px solid {BORDER}; padding: 4px 6px; }}
"""

"""A window frame without Windows' title bar, so the page draws its own (ui/web .titlebar).

Windows' title bar is drawn by the system, apart from the page, and can't change in step with it:
switching themes, it always showed up a frame or two early or late. So the page draws the whole
window and Windows only keeps the frame: the shadow, rounded corners, resizing, snapping and
the system menu (Alt+Space). The top strip of the page, except the page's window buttons, acts
as the title bar for dragging, double-click to maximise and snapping.
"""
import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = ctypes.c_ssize_t
user32.GetDpiForWindow.argtypes = [wintypes.HWND]
user32.GetDpiForWindow.restype = wintypes.UINT
user32.GetSystemMetricsForDpi.argtypes = [ctypes.c_int, wintypes.UINT]
user32.ScreenToClient.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.IsZoomed.argtypes = [wintypes.HWND]

WM_NCCALCSIZE, WM_NCHITTEST = 0x0083, 0x0084
HTCAPTION, HTTOP, HTTOPLEFT, HTTOPRIGHT = 2, 12, 13, 14
SM_CXFRAME, SM_CYFRAME, SM_CXPADDEDBORDER = 32, 33, 92
SWP_FRAME_ONLY = 0x0002 | 0x0001 | 0x0004 | 0x0010 | 0x0020  # no move/size/z-order/activate; frame changed

# Must match .titlebar in web/style.css (CSS px).
TITLE_H = 36
BUTTONS_W = 3 * 46


class NCCALCSIZE_PARAMS(ctypes.Structure):
    _fields_ = [("rgrc", wintypes.RECT * 3), ("lppos", ctypes.c_void_p)]


def _border(hwnd, horizontal: bool) -> int:
    """The resize border's thickness in physical pixels (outside the window's visible edge)."""
    dpi = user32.GetDpiForWindow(hwnd) or 96
    size = user32.GetSystemMetricsForDpi(SM_CXFRAME if horizontal else SM_CYFRAME, dpi)
    return size + user32.GetSystemMetricsForDpi(SM_CXPADDEDBORDER, dpi)


def refresh(hwnd):
    """Makes Windows measure the frame again, after the window is created."""
    user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, SWP_FRAME_ONLY)


def handle(msg: wintypes.MSG, scale: float) -> int | None:
    """The result for a frame message, or None to leave it to Qt and Windows. `scale` is the
    window's device pixel ratio (CSS px to physical)."""
    hwnd = msg.hWnd
    if msg.message == WM_NCCALCSIZE and msg.wParam:
        params = NCCALCSIZE_PARAMS.from_address(msg.lParam)
        top = params.rgrc[0].top
        # Windows sets the side and bottom borders; the top keeps no title bar.
        user32.DefWindowProcW(hwnd, msg.message, msg.wParam, msg.lParam)
        # Maximised, the window reaches past the screen by its border; keep the page on screen.
        params.rgrc[0].top = top + (_border(hwnd, False) if user32.IsZoomed(hwnd) else 0)
        return 0
    if msg.message == WM_NCHITTEST:
        pt = wintypes.POINT(ctypes.c_short(msg.lParam & 0xFFFF).value,
                            ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value)
        user32.ScreenToClient(hwnd, ctypes.byref(pt))
        client = wintypes.RECT()
        user32.GetClientRect(hwnd, ctypes.byref(client))
        if pt.y < 0 or pt.x < 0 or pt.x >= client.right:
            return None  # the borders around the page: Windows' own
        if not user32.IsZoomed(hwnd) and pt.y < _border(hwnd, False) // 2:
            # The top edge resizes, as the title bar's did. Corners reach a little further in.
            corner = _border(hwnd, True) * 2
            return HTTOPLEFT if pt.x < corner else HTTOPRIGHT if pt.x >= client.right - corner else HTTOP
        if pt.y < TITLE_H * scale and pt.x < client.right - BUTTONS_W * scale:
            return HTCAPTION
    return None

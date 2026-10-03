"""Types text into whatever app has focus.

Pastes through the clipboard (fast, and editors don't auto-complete or auto-close brackets on
it), then puts back everything that was on the clipboard: text, an image, copied files, rich
text. Typing the text as keystrokes is only a last resort: apps like Electron ones take typed
keystrokes slowly and in bursts, and can drop some.
"""
import ctypes
import os
import threading
import time
from ctypes import wintypes
from pathlib import Path

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x2
KEYEVENTF_UNICODE = 0x4
VK_CONTROL, VK_V = 0x11, 0x56
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
TOKEN_QUERY = 0x8
TOKEN_INTEGRITY_LEVEL = 25  # TOKEN_INFORMATION_CLASS

# Time the target app gets to read the clipboard before the old contents come back.
RESTORE_AFTER_S = 0.5
# Clipboard formats that hold GDI handles rather than memory, which a snapshot can't copy.
# Windows makes CF_BITMAP again from CF_DIB, which is copied. (CF_ENHMETAFILE is copied apart.)
CF_BITMAP, CF_METAFILEPICT, CF_PALETTE, CF_ENHMETAFILE = 2, 3, 9, 14
_UNCOPYABLE = {CF_BITMAP, CF_METAFILEPICT, CF_PALETTE, 0x80, 0x82, 0x83, 0x8E}  # + owner/display
# Past this, the clipboard isn't copied (and the text is typed instead): a huge copied image.
SNAPSHOT_MAX_BYTES = 256 << 20

for name, args, res in [
    ("OpenClipboard", [wintypes.HWND], wintypes.BOOL),
    ("CloseClipboard", [], wintypes.BOOL),
    ("EmptyClipboard", [], wintypes.BOOL),
    ("GetClipboardData", [wintypes.UINT], wintypes.HANDLE),
    ("SetClipboardData", [wintypes.UINT, wintypes.HANDLE], wintypes.HANDLE),
    ("IsClipboardFormatAvailable", [wintypes.UINT], wintypes.BOOL),
    ("CountClipboardFormats", [], ctypes.c_int),
    ("EnumClipboardFormats", [wintypes.UINT], wintypes.UINT),
    ("GetClipboardSequenceNumber", [], wintypes.DWORD),
    ("RegisterClipboardFormatW", [wintypes.LPCWSTR], wintypes.UINT),
    ("GetForegroundWindow", [], wintypes.HWND),
    ("GetWindowThreadProcessId", [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)], wintypes.DWORD),
]:
    fn = getattr(user32, name)
    fn.argtypes, fn.restype = args, res
for name, args, res in [
    ("GlobalAlloc", [wintypes.UINT, ctypes.c_size_t], wintypes.HGLOBAL),
    ("GlobalLock", [wintypes.HGLOBAL], wintypes.LPVOID),
    ("GlobalUnlock", [wintypes.HGLOBAL], wintypes.BOOL),
    ("GlobalFree", [wintypes.HGLOBAL], wintypes.HGLOBAL),
    ("GlobalSize", [wintypes.HGLOBAL], ctypes.c_size_t),
    ("OpenProcess", [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
    ("CloseHandle", [wintypes.HANDLE], wintypes.BOOL),
    ("QueryFullProcessImageNameW", [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
    ("GetCurrentProcess", [], wintypes.HANDLE),
]:
    fn = getattr(kernel32, name)
    fn.argtypes, fn.restype = args, res
for name, args, res in [
    ("OpenProcessToken", [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)], wintypes.BOOL),
    ("GetTokenInformation", [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
    ("GetSidSubAuthorityCount", [ctypes.c_void_p], ctypes.POINTER(ctypes.c_ubyte)),
    ("GetSidSubAuthority", [ctypes.c_void_p, wintypes.DWORD], ctypes.POINTER(wintypes.DWORD)),
]:
    fn = getattr(advapi32, name)
    fn.argtypes, fn.restype = args, res


gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
gdi32.CopyEnhMetaFileW.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR]
gdi32.CopyEnhMetaFileW.restype = wintypes.HANDLE
gdi32.DeleteEnhMetaFile.argtypes = [wintypes.HANDLE]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD), ("hwndActive", wintypes.HWND),
                ("hwndFocus", wintypes.HWND), ("hwndCapture", wintypes.HWND),
                ("hwndMenuOwner", wintypes.HWND), ("hwndMoveSize", wintypes.HWND),
                ("hwndCaret", wintypes.HWND), ("rcCaret", wintypes.RECT)]


user32.GetGUIThreadInfo.argtypes = [wintypes.DWORD, ctypes.POINTER(GUITHREADINFO)]
user32.GetGUIThreadInfo.restype = wintypes.BOOL

# Keeps our temporary clipboard text out of Win+V clipboard history.
_EXCLUDE_FROM_HISTORY = [
    user32.RegisterClipboardFormatW("ExcludeClipboardContentFromMonitorProcessing"),
    user32.RegisterClipboardFormatW("CanIncludeInClipboardHistory"),
]


def _key(vk=0, scan=0, flags=0) -> INPUT:
    return INPUT(type=INPUT_KEYBOARD, u=_INPUTUNION(ki=KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags)))


def _send(inputs: list[INPUT]):
    arr = (INPUT * len(inputs))(*inputs)
    user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))


def _open_clipboard() -> bool:
    # Clipboard watchers (clipboard history, other dictation apps) open it right after every
    # change and can hold it for a few hundred ms.
    for _ in range(100):
        if user32.OpenClipboard(None):
            return True
        time.sleep(0.01)
    return False


def _global(data: bytes):
    h = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
    ptr = kernel32.GlobalLock(h)
    ctypes.memmove(ptr, data, len(data))
    kernel32.GlobalUnlock(h)
    return h


def _snapshot() -> list[tuple[int, bytes | int]] | None:
    """Everything on the clipboard, format by format, to put back after pasting: (format, bytes),
    or (CF_ENHMETAFILE, a copied handle). None if it can't be opened or is too big to copy."""
    if not _open_clipboard():
        return None
    saved: list[tuple[int, bytes | int]] = []
    total, fmt = 0, 0
    try:
        while fmt := user32.EnumClipboardFormats(fmt):
            if fmt in _UNCOPYABLE or 0x200 <= fmt <= 0x3FF:  # private and GDI-object ranges
                continue
            h = user32.GetClipboardData(fmt)
            if not h:
                continue
            if fmt == CF_ENHMETAFILE:
                copy = gdi32.CopyEnhMetaFileW(h, None)
                if copy:
                    saved.append((fmt, copy))
                continue
            size = kernel32.GlobalSize(h)
            total += size
            if total > SNAPSHOT_MAX_BYTES:
                _discard(saved)
                return None
            ptr = kernel32.GlobalLock(h)
            if not ptr:
                continue
            try:
                saved.append((fmt, ctypes.string_at(ptr, size)))
            finally:
                kernel32.GlobalUnlock(h)
        return saved
    finally:
        user32.CloseClipboard()


def _discard(saved):
    for fmt, data in saved:
        if fmt == CF_ENHMETAFILE:
            gdi32.DeleteEnhMetaFile(data)


def _restore(saved) -> bool:
    """Puts a snapshot back, kept out of clipboard history (it's already in there)."""
    if not _open_clipboard():
        _discard(saved)
        return False
    try:
        user32.EmptyClipboard()
        for fmt, data in saved:
            if fmt == CF_ENHMETAFILE:
                if not user32.SetClipboardData(fmt, data):
                    gdi32.DeleteEnhMetaFile(data)
                continue
            if not data:
                continue
            h = _global(data)
            if not user32.SetClipboardData(fmt, h):
                kernel32.GlobalFree(h)
        for fmt in _EXCLUDE_FROM_HISTORY:
            h = _global(b"\0\0\0\0")
            if not user32.SetClipboardData(fmt, h):
                kernel32.GlobalFree(h)
        return True
    finally:
        user32.CloseClipboard()


def _write_clipboard(text: str | None, temporary=True) -> bool:
    """Temporary text (ours, only there to be pasted) is kept out of clipboard history."""
    if not _open_clipboard():
        return False
    try:
        user32.EmptyClipboard()
        if text is not None:
            h = _global((text + "\0").encode("utf-16-le"))
            if not user32.SetClipboardData(CF_UNICODETEXT, h):
                kernel32.GlobalFree(h)
                return False
        for fmt in _EXCLUDE_FROM_HISTORY if temporary else []:
            h = _global(b"\0\0\0\0")
            if not user32.SetClipboardData(fmt, h):
                kernel32.GlobalFree(h)
        return True
    finally:
        user32.CloseClipboard()


def copy(text: str) -> bool:
    """Puts text on the clipboard to stay, like the user copied it."""
    return _write_clipboard(text, temporary=False)


def _wait_readable(timeout=0.5) -> bool:
    """Waits until the clipboard text can be read again.

    Clipboard watchers open the clipboard right after a change; a paste sent during that moment
    would find it locked and paste nothing.
    """
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if user32.OpenClipboard(None):
            try:
                if user32.GetClipboardData(CF_UNICODETEXT):
                    return True
            finally:
                user32.CloseClipboard()
        time.sleep(0.005)
    return False


def tap(vk: int):
    """Presses and releases one key."""
    _send([_key(vk), _key(vk, flags=KEYEVENTF_KEYUP)])


def type_keys(text: str):
    """Types text as Unicode keystrokes (no clipboard)."""
    units = text.encode("utf-16-le")
    inputs = []
    for i in range(0, len(units), 2):
        code = int.from_bytes(units[i:i + 2], "little")
        inputs += [_key(scan=code, flags=KEYEVENTF_UNICODE),
                   _key(scan=code, flags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)]
    _send(inputs)


def paste(text: str, space_before=False) -> str:
    """Puts text into the focused app. Returns how: "paste" or "type", or "copy" when the app
    runs as administrator: Windows drops our keystrokes there, so the text is left on the
    clipboard for the user to paste instead."""
    if foreground_elevated():
        copy(text)
        return "copy"
    if space_before:
        text = " " + text
    previous = _snapshot()
    if previous is None or not _write_clipboard(text):
        if previous is not None:
            _restore(previous)  # the failed write may have emptied it
        type_keys(text)
        return "type"
    ours = user32.GetClipboardSequenceNumber()
    _wait_readable()
    _send([_key(VK_CONTROL), _key(VK_V), _key(VK_V, flags=KEYEVENTF_KEYUP), _key(VK_CONTROL, flags=KEYEVENTF_KEYUP)])

    def restore():
        # Only if nothing else has been copied in the meantime.
        if user32.GetClipboardSequenceNumber() == ours:
            _restore(previous)
        else:
            _discard(previous)

    t = threading.Timer(RESTORE_AFTER_S, restore)
    t.daemon = True
    t.start()
    return "paste"


WINEVENTPROC = ctypes.WINFUNCTYPE(None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND, wintypes.LONG,
                                  wintypes.LONG, wintypes.DWORD, wintypes.DWORD)
user32.SetWinEventHook.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.HMODULE, WINEVENTPROC,
                                   wintypes.DWORD, wintypes.DWORD, wintypes.DWORD]
user32.SetWinEventHook.restype = wintypes.HANDLE
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.IsWindow.argtypes = [wintypes.HWND]
EVENT_SYSTEM_FOREGROUND = 0x3
WINEVENT_SKIPOWNPROCESS = 0x2
# The taskbar, its tray overflow and the desktop: where the user goes to reach Murmur's tray menu.
_SHELL_CLASSES = {"Shell_TrayWnd", "Shell_SecondaryTrayWnd", "NotifyIconOverflowWindow",
                  "TopLevelWindowForOverflowXamlIsland", "Progman", "WorkerW"}


class LastAppWindow:
    """Remembers the last app window the user was in, other than Murmur and the taskbar, so a
    tray menu command can go back to it. Create it on the UI thread: the events arrive there."""

    def __init__(self):
        self.hwnd = None
        self._proc = WINEVENTPROC(self._changed)  # kept referenced so it isn't garbage collected
        self._hook = user32.SetWinEventHook(EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_FOREGROUND, None,
                                            self._proc, 0, 0, WINEVENT_SKIPOWNPROCESS)
        self._changed(None, 0, user32.GetForegroundWindow(), 0, 0, 0, 0)

    def _changed(self, hook, event, hwnd, obj, child, thread, time_ms):
        name = ctypes.create_unicode_buffer(64)
        if (hwnd and user32.GetClassNameW(hwnd, name, 64) and name.value not in _SHELL_CLASSES
                and window_pid(hwnd) != os.getpid()):
            self.hwnd = hwnd

    def activate(self) -> bool:
        """Brings that window back to the front. False if it's gone or Windows refused."""
        if not self.hwnd or not user32.IsWindow(self.hwnd):
            return False
        user32.SetForegroundWindow(self.hwnd)
        return user32.GetForegroundWindow() == self.hwnd


def window_pid(hwnd) -> int:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def foreground_pid() -> int:
    return window_pid(user32.GetForegroundWindow())


def focus_window() -> tuple[int, int] | None:
    """(foreground window, its focused control): where typed text goes, as far as Windows knows."""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    tid = user32.GetWindowThreadProcessId(hwnd, None)
    info = GUITHREADINFO(cbSize=ctypes.sizeof(GUITHREADINFO))
    focus = info.hwndFocus if user32.GetGUIThreadInfo(tid, ctypes.byref(info)) else None
    return hwnd, focus or 0


def foreground_app() -> str | None:
    """File name of the focused app, like "chrome.exe"."""
    pid = foreground_pid()
    if pid == os.getpid():
        return "Murmur"  # the try-it box in Murmur's own window
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return None
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(len(buf))
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return Path(buf.value).name
        return None
    finally:
        kernel32.CloseHandle(h)


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD)]


user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
user32.MonitorFromWindow.restype = wintypes.HMONITOR
user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.IsZoomed.argtypes = [wintypes.HWND]
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = ctypes.c_long
MONITOR_DEFAULTTONULL, MONITOR_DEFAULTTONEAREST = 0, 2
GWL_STYLE, WS_CAPTION = -16, 0x00C00000
FULL_SLACK = 2  # pixels


def monitor_of(hwnd) -> int:
    return user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST) or 0


def fullscreen_monitor() -> int | None:
    """The monitor the foreground window fills entirely (a video, a game, a slideshow), or None.
    Not the desktop, nor Murmur's own windows."""
    hwnd = user32.GetForegroundWindow()
    if not hwnd or window_pid(hwnd) == os.getpid():
        return None
    name = ctypes.create_unicode_buffer(64)
    if user32.GetClassNameW(hwnd, name, 64) and name.value in _SHELL_CLASSES:
        return None
    return filled_monitor(hwnd)


def filled_monitor(hwnd) -> int | None:
    """The monitor `hwnd` covers entirely, or None. A maximised window with a title bar doesn't
    count, even where an auto-hidden taskbar lets it cover the screen. A fullscreen one has no
    title bar, but may still say it's maximised (Chrome's does), and stop FULL_SLACK pixels short
    of an auto-hidden taskbar's edge."""
    if not hwnd:
        return None
    style = user32.GetWindowLongW(hwnd, GWL_STYLE) & 0xFFFFFFFF
    if user32.IsZoomed(hwnd) and style & WS_CAPTION == WS_CAPTION:
        return None
    monitor = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONULL)
    rect, info = wintypes.RECT(), MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
    if (not monitor or not user32.GetWindowRect(hwnd, ctypes.byref(rect))
            or not user32.GetMonitorInfoW(monitor, ctypes.byref(info))):
        return None
    m = info.rcMonitor
    s = FULL_SLACK
    covers = (rect.left <= m.left + s and rect.top <= m.top + s
              and rect.right >= m.right - s and rect.bottom >= m.bottom - s)
    return monitor if covers else None


def _integrity(process) -> int | None:
    """Integrity level of a process handle: 0x2000 normal, 0x3000 administrator."""
    token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(process, TOKEN_QUERY, ctypes.byref(token)):
        return None
    try:
        buf = ctypes.create_string_buffer(64)
        size = wintypes.DWORD()
        if not advapi32.GetTokenInformation(token, TOKEN_INTEGRITY_LEVEL, buf, len(buf), ctypes.byref(size)):
            return None
        sid = ctypes.cast(buf, ctypes.POINTER(ctypes.c_void_p))[0]  # TOKEN_MANDATORY_LABEL.Label.Sid
        count = advapi32.GetSidSubAuthorityCount(sid)[0]
        return advapi32.GetSidSubAuthority(sid, count - 1)[0]
    finally:
        kernel32.CloseHandle(token)


_own_integrity = _integrity(kernel32.GetCurrentProcess())


def foreground_elevated() -> bool:
    """Whether the focused app runs at a higher integrity level than Murmur (as administrator),
    where Windows silently drops the keystrokes we send."""
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, foreground_pid())
    if not h:
        return False
    try:
        level = _integrity(h)
    finally:
        kernel32.CloseHandle(h)
    return level is not None and _own_integrity is not None and level > _own_integrity

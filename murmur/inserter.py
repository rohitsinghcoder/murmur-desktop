"""Types text into whatever app has focus.

Pastes through the clipboard (fast, and editors don't auto-complete or auto-close brackets on
it), then puts the previous clipboard text back. If the clipboard holds something that isn't
text (an image, copied files), it is left alone and the text is typed as keystrokes instead.
"""
import ctypes
import os
import threading
import time
from ctypes import wintypes
from pathlib import Path

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x2
KEYEVENTF_UNICODE = 0x4
VK_CONTROL, VK_V = 0x11, 0x56
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

# Time the target app gets to read the clipboard before the old contents come back.
RESTORE_AFTER_S = 0.5

for name, args, res in [
    ("OpenClipboard", [wintypes.HWND], wintypes.BOOL),
    ("CloseClipboard", [], wintypes.BOOL),
    ("EmptyClipboard", [], wintypes.BOOL),
    ("GetClipboardData", [wintypes.UINT], wintypes.HANDLE),
    ("SetClipboardData", [wintypes.UINT, wintypes.HANDLE], wintypes.HANDLE),
    ("IsClipboardFormatAvailable", [wintypes.UINT], wintypes.BOOL),
    ("CountClipboardFormats", [], ctypes.c_int),
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
    ("OpenProcess", [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
    ("CloseHandle", [wintypes.HANDLE], wintypes.BOOL),
    ("QueryFullProcessImageNameW", [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
]:
    fn = getattr(kernel32, name)
    fn.argtypes, fn.restype = args, res


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


def _read_clipboard() -> tuple[bool, str | None]:
    """(restorable, text). Restorable when the clipboard is empty or holds text."""
    if not _open_clipboard():
        return False, None
    try:
        if user32.CountClipboardFormats() == 0:
            return True, None
        if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            return False, None
        h = user32.GetClipboardData(CF_UNICODETEXT)
        ptr = kernel32.GlobalLock(h)
        if not ptr:
            return False, None
        try:
            return True, ctypes.wstring_at(ptr)
        finally:
            kernel32.GlobalUnlock(h)
    finally:
        user32.CloseClipboard()


def _write_clipboard(text: str | None) -> bool:
    if not _open_clipboard():
        return False
    try:
        user32.EmptyClipboard()
        if text is not None:
            h = _global((text + "\0").encode("utf-16-le"))
            if not user32.SetClipboardData(CF_UNICODETEXT, h):
                kernel32.GlobalFree(h)
                return False
        for fmt in _EXCLUDE_FROM_HISTORY:
            h = _global(b"\0\0\0\0")
            if not user32.SetClipboardData(fmt, h):
                kernel32.GlobalFree(h)
        return True
    finally:
        user32.CloseClipboard()


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


def paste(text: str) -> str:
    """Puts text into the focused app. Returns how: "paste" or "type"."""
    restorable, previous = _read_clipboard()
    if not restorable or not _write_clipboard(text):
        type_keys(text)
        return "type"
    ours = user32.GetClipboardSequenceNumber()
    _wait_readable()
    _send([_key(VK_CONTROL), _key(VK_V), _key(VK_V, flags=KEYEVENTF_KEYUP), _key(VK_CONTROL, flags=KEYEVENTF_KEYUP)])

    def restore():
        # Only if nothing else has been copied in the meantime.
        if user32.GetClipboardSequenceNumber() == ours:
            _write_clipboard(previous)

    t = threading.Timer(RESTORE_AFTER_S, restore)
    t.daemon = True
    t.start()
    return "paste"


def foreground_app() -> str | None:
    """File name of the focused app, like "chrome.exe"."""
    hwnd = user32.GetForegroundWindow()
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value == os.getpid():
        return "Murmur"  # the try-it box in Murmur's own window
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
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

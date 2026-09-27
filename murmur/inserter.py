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


def foreground_pid() -> int:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), ctypes.byref(pid))
    return pid.value


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

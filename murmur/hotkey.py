"""Global hold-to-talk key, via a low-level Windows keyboard hook.

- Hold the key: listen. Release: finish and type the text.
- Tap it twice quickly: hands-free. Tap once more to finish.
- Press any other key while holding: it was a shortcut (Right Ctrl+C...), so cancel.
- Esc while listening: cancel.
"""
import ctypes
import threading
import time
from ctypes import wintypes
from typing import Callable

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x100, 0x101, 0x104, 0x105
WM_QUIT = 0x12
LLKHF_INJECTED = 0x10
VK_ESCAPE = 0x1B
VK_RCONTROL = 0xA3

# A press shorter than this is a tap, not a hold.
TAP_S = 0.3
# Time allowed between the two taps of a double tap.
DOUBLE_TAP_S = 0.35


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE

IDLE, HOLDING, TAP_WAIT, LOCKING, LOCKED, UNLOCKING = range(6)


class HoldToTalk:
    """Calls on_start / on_finish / on_cancel / on_lock. Callbacks must return quickly."""

    def __init__(
        self,
        on_start: Callable[[], None],
        on_finish: Callable[[], None],
        on_cancel: Callable[[], None],
        on_lock: Callable[[], None] = lambda: None,
        vk: int = VK_RCONTROL,
    ):
        self.on_start = on_start
        self.on_finish = on_finish
        self.on_cancel = on_cancel
        self.on_lock = on_lock
        self.vk = vk
        self._state = IDLE
        self._down = False
        self._down_at = 0.0
        self._timer: threading.Timer | None = None
        self._lock = threading.RLock()
        self._thread_id = 0
        self._proc = HOOKPROC(self._hook)  # kept referenced so it isn't garbage collected

    def start(self):
        ready = threading.Event()
        threading.Thread(target=self._loop, args=(ready,), name="murmur-hotkey", daemon=True).start()
        ready.wait()

    def stop(self):
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)

    def reset(self):
        """Back to idle, e.g. after dictation ended some other way."""
        with self._lock:
            self._cancel_timer()
            self._state = IDLE

    def _loop(self, ready: threading.Event):
        self._thread_id = kernel32.GetCurrentThreadId()
        hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, kernel32.GetModuleHandleW(None), 0)
        ready.set()
        if not hook:
            raise ctypes.WinError(ctypes.get_last_error())
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            pass
        user32.UnhookWindowsHookEx(hook)

    def _hook(self, code, wparam, lparam):
        if code >= 0:
            kb = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            # Ignore our own Ctrl+V and anything else typed by software.
            if not kb.flags & LLKHF_INJECTED:
                down = wparam in (WM_KEYDOWN, WM_SYSKEYDOWN)
                if self._on_key(kb.vkCode, down):
                    return 1  # swallow
        return user32.CallNextHookEx(None, code, wparam, lparam)

    def _on_key(self, vk: int, down: bool) -> bool:
        """Returns True to swallow the key."""
        with self._lock:
            if vk == self.vk:
                if down:
                    if self._down:
                        return False  # auto-repeat
                    self._down = True
                    self._pressed()
                else:
                    self._down = False
                    self._released()
                return False
            if not down or self._state == IDLE:
                return False
            if vk == VK_ESCAPE:
                self._cancel()
                return True
            if self._state == HOLDING:
                # Another key while holding: a shortcut, not dictation.
                self._cancel()
            return False

    def _pressed(self):
        if self._state == IDLE:
            self._state = HOLDING
            self._down_at = time.monotonic()
            self.on_start()
        elif self._state == TAP_WAIT:
            # Second tap of a double tap: hands-free.
            self._cancel_timer()
            self._state = LOCKING
            self.on_lock()
        elif self._state == LOCKED:
            self._state = UNLOCKING

    def _released(self):
        # Finishing on release (not press) means Ctrl is up again before the text is pasted.
        if self._state == HOLDING:
            if time.monotonic() - self._down_at < TAP_S:
                self._state = TAP_WAIT
                self._timer = threading.Timer(DOUBLE_TAP_S, self._tap_expired)
                self._timer.daemon = True
                self._timer.start()
            else:
                self._state = IDLE
                self.on_finish()
        elif self._state == LOCKING:
            self._state = LOCKED
        elif self._state == UNLOCKING:
            self._state = IDLE
            self.on_finish()

    def _tap_expired(self):
        with self._lock:
            if self._state == TAP_WAIT:
                # A single short tap: too short to be dictation.
                self._state = IDLE
                self.on_cancel()

    def _cancel(self):
        self._cancel_timer()
        self._state = IDLE
        self.on_cancel()

    def _cancel_timer(self):
        if self._timer:
            self._timer.cancel()
            self._timer = None

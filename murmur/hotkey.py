"""Global hold-to-talk hotkey, via a low-level Windows keyboard hook.

- Hold the hotkey: listen. Release: finish and type the text.
- Tap it twice quickly: hands-free. Tap once more to finish.
- Press any other key while holding: it was a shortcut (Right Ctrl+C...), so cancel.
- Esc while listening: cancel.

A hotkey is a list of key names: a single key ("rctrl", "vk_78" for F9) or a combo
("ctrl", "shift", "vk_20" for Ctrl+Shift+Space). Modifiers in a combo match either side.
"""
import ctypes
import threading
import time
from ctypes import wintypes
from typing import Callable

from . import inserter

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x100, 0x101, 0x104, 0x105
WM_QUIT = 0x12
LLKHF_INJECTED = 0x10
VK_ESCAPE = 0x1B
VK_RCONTROL = 0xA3
VK_LCONTROL = 0xA2
# Unassigned key. Pressed after Win or Alt so releasing them doesn't open Start or a menu bar.
VK_DUMMY = 0xE8
# AltGr sends a fake Left Ctrl with this scan code before Right Alt.
ALTGR_FAKE_CTRL_SCAN = 0x21D

# A press shorter than this is a tap, not a hold.
TAP_S = 0.3
# Time allowed between the two taps of a double tap.
DOUBLE_TAP_S = 0.35

SIDED = {
    "lctrl": 0xA2, "rctrl": 0xA3, "lalt": 0xA4, "ralt": 0xA5,
    "lshift": 0xA0, "rshift": 0xA1, "lwin": 0x5B, "rwin": 0x5C,
}
GENERIC = {
    "ctrl": {0xA2, 0xA3}, "alt": {0xA4, 0xA5}, "shift": {0xA0, 0xA1}, "win": {0x5B, 0x5C},
}
MODIFIER_VKS = set(SIDED.values())
_GENERIC_OF = {vk: name for name, vks in GENERIC.items() for vk in vks}
LABELS = {
    "lctrl": "Left Ctrl", "rctrl": "Right Ctrl", "lalt": "Left Alt", "ralt": "Right Alt",
    "lshift": "Left Shift", "rshift": "Right Shift", "lwin": "Left Win", "rwin": "Right Win",
    "ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "win": "Win",
}
_VK_LABELS = {
    0x08: "Backspace", 0x09: "Tab", 0x0D: "Enter", 0x13: "Pause", 0x14: "Caps Lock", 0x20: "Space",
    0x21: "Page Up", 0x22: "Page Down", 0x23: "End", 0x24: "Home", 0x25: "Left", 0x26: "Up",
    0x27: "Right", 0x28: "Down", 0x2C: "Print Screen", 0x2D: "Insert", 0x2E: "Delete",
    0x5D: "Menu", 0x90: "Num Lock", 0x91: "Scroll Lock",
    0xBA: ";", 0xBB: "=", 0xBC: ",", 0xBD: "-", 0xBE: ".", 0xBF: "/", 0xC0: "`",
    0xDB: "[", 0xDC: "\\", 0xDD: "]", 0xDE: "'",
}
# Keys that are fine on their own: nobody types with them.
_SOLO_OK = set(range(0x70, 0x88)) | {0x13, 0x14, 0x2D, 0x5D, 0x91}


def _vk_of(name: str) -> int:
    return int(name[3:], 16)


def key_vks(name: str) -> set[int]:
    if name in GENERIC:
        return GENERIC[name]
    if name in SIDED:
        return {SIDED[name]}
    return {_vk_of(name)}


def label(name: str) -> str:
    if name in LABELS:
        return LABELS[name]
    vk = _vk_of(name)
    if 0x70 <= vk <= 0x87:
        return f"F{vk - 0x6F}"
    if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:
        return chr(vk)
    if 0x60 <= vk <= 0x69:
        return f"Num {vk - 0x60}"
    return _VK_LABELS.get(vk, f"Key {vk:#04x}")


def describe(hotkey: list[str]) -> str:
    """Like "Right Ctrl" or "Ctrl + Shift + Space"."""
    return " + ".join(label(k) for k in hotkey)


def from_pressed(vks: list[int]) -> list[str]:
    """Hotkey names for keys pressed together, in the order they were pressed."""
    if len(vks) == 1:
        vk = vks[0]
        return [next(n for n, v in SIDED.items() if v == vk)] if vk in MODIFIER_VKS else [f"vk_{vk:02x}"]
    mods = {_GENERIC_OF[vk] for vk in vks if vk in MODIFIER_VKS}
    others = [f"vk_{vk:02x}" for vk in vks if vk not in MODIFIER_VKS]
    return [m for m in ("ctrl", "alt", "shift", "win") if m in mods] + others


def problem(hotkey: list[str]) -> str | None:
    """Why a hotkey would get in the way of normal typing, or None if it's fine."""
    others = [_vk_of(k) for k in hotkey if k.startswith("vk_")]
    mods = [k for k in hotkey if not k.startswith("vk_")]
    if VK_ESCAPE in others:
        return "Esc is used to cancel dictation. Pick another key."
    if not mods:
        if len(others) == 1 and others[0] in _SOLO_OK:
            return None
        return "That key is used for typing. Pick one like Right Ctrl or F9, or add Ctrl, Alt, Shift or Win."
    if mods == ["shift"] and others:
        return "Shift + a key is used for typing. Add Ctrl, Alt or Win."
    return None


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
        hotkey: list[str] | None = None,
    ):
        self.on_start = on_start
        self.on_finish = on_finish
        self.on_cancel = on_cancel
        self.on_lock = on_lock
        self._state = IDLE
        self._down: set[int] = set()
        self._swallowed: set[int] = set()
        self._down_at = 0.0
        # When a key other than the hotkey was last pressed: typing may have moved the caret.
        self.typed_at = 0.0
        self._timer: threading.Timer | None = None
        self._lock = threading.RLock()
        self._thread_id = 0
        self._proc = HOOKPROC(self._hook)  # kept referenced so it isn't garbage collected
        self._recorder: Callable[[list[int] | None], None] | None = None
        self._recorded: list[int] = []
        self.set_hotkey(hotkey or ["rctrl"])

    def set_hotkey(self, hotkey: list[str]):
        with self._lock:
            self.hotkey = list(hotkey)
            self._parts = [key_vks(k) for k in hotkey]
            self._all_vks = set().union(*self._parts)
            # Keys that would type something or trigger a shortcut in the focused app.
            self._swallow = {_vk_of(k) for k in hotkey if k.startswith("vk_")}
            self._needs_dummy = any(k in ("alt", "lalt", "ralt", "win", "lwin", "rwin") for k in hotkey)
            self._state = IDLE
            self._cancel_timer()

    def record(self, on_recorded: Callable[[list[int] | None], None]):
        """Captures the next key or combo pressed (virtual-key codes), or None if Esc.

        While recording, keys don't reach other apps and don't start dictation.
        """
        with self._lock:
            self._recorder = on_recorded
            self._recorded = []

    def stop_recording(self):
        with self._lock:
            self._recorder = None

    def start(self):
        ready = threading.Event()
        threading.Thread(target=self._loop, args=(ready,), name="murmur-hotkey", daemon=True).start()
        ready.wait()

    def stop(self):
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)

    def hands_free(self):
        """Dictation was started some other way (clicking the bar): the next tap finishes it."""
        with self._lock:
            self._cancel_timer()
            self._state = LOCKED

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
            # Ignore our own Ctrl+V and anything else typed by software, and AltGr's fake Ctrl.
            fake = kb.vkCode == VK_LCONTROL and kb.scanCode == ALTGR_FAKE_CTRL_SCAN
            if not kb.flags & LLKHF_INJECTED and not fake:
                down = wparam in (WM_KEYDOWN, WM_SYSKEYDOWN)
                if self._on_key(kb.vkCode, down):
                    return 1  # swallow
        return user32.CallNextHookEx(None, code, wparam, lparam)

    def _active(self) -> bool:
        return all(part & self._down for part in self._parts)

    def _on_key(self, vk: int, down: bool) -> bool:
        """Returns True to swallow the key."""
        with self._lock:
            if self._recorder:
                return self._record_key(vk, down)
            repeat = down and vk in self._down
            was = self._active()
            if down:
                self._down.add(vk)
            else:
                self._down.discard(vk)
            now = self._active()

            if vk in self._all_vks:
                if not repeat and now and not was:
                    if self._needs_dummy:
                        inserter.tap(VK_DUMMY)
                    self._pressed()
                elif was and not now:
                    self._released()
                # Swallow the non-modifier key of a combo (Space in Ctrl+Shift+Space) so it
                # doesn't type into the app, along with its release.
                if vk in self._swallow:
                    if down and now:
                        self._swallowed.add(vk)
                        return True
                    if not down and vk in self._swallowed:
                        self._swallowed.discard(vk)
                        return True
                return False

            if down:
                self.typed_at = time.monotonic()
            if not down or self._state == IDLE:
                return False
            if vk == VK_ESCAPE:
                self._cancel()
                return True
            if self._state == HOLDING:
                # Another key while holding: a shortcut, not dictation.
                self._cancel()
            return False

    def _record_key(self, vk: int, down: bool) -> bool:
        if down:
            if vk == VK_ESCAPE:
                recorder, self._recorder = self._recorder, None
                self._down.clear()
                recorder(None)
                return True
            self._down.add(vk)
            if vk not in self._recorded:
                self._recorded.append(vk)
        else:
            self._down.discard(vk)
            if not self._down and self._recorded:
                recorder, self._recorder = self._recorder, None
                recorder(list(self._recorded))
        return True

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
        # Finishing on release (not press) means the keys are up again before the text is pasted.
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

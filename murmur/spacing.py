"""Whether a dictation needs a space in front of it, so two in a row don't run together
("Hello there.How are you?"). Like the Android app, which adds one when the character before
the cursor isn't whitespace.

The characters before the caret are read with Windows UI Automation. Apps can be slow to answer,
or hang, so that happens on a thread of its own with a strict time limit. When it can't tell, a
dictation right after the last one into the same window, with no typing in between, gets a space.
"""
import ctypes
import logging
import math
import os
import sys
import time
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from ctypes import wintypes

from . import inserter

log = logging.getLogger(__name__)

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.SendMessageTimeoutW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
                                       wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)]
user32.SendMessageTimeoutW.restype = wintypes.LPARAM
WM_GETTEXT, WM_GETTEXTLENGTH, EM_GETSEL = 0x0D, 0x0E, 0xB0
SMTO_ABORTIFHUNG = 0x2

# No space after these: the dictation continues what they open.
OPENERS = "([{<“‘«¿¡/@#$—-"
# Dictated text starting with these attaches to what comes before it.
ATTACHES = ".,;:!?)]}>”’»%…"
QUOTES = "\"'"
# How long the fallback trusts that the caret is still right after the last dictation.
FOLLOW_S = 120.0
# The longest a dictation waits for the app to say what's before the caret.
READ_TIMEOUT_S = 0.15


def needs_space(text: str, before: str | None, follows_last=False) -> bool:
    """`before`: the (up to two) characters before the caret, "" at the start of a field, or None
    if unknown. `follows_last`: the last dictation went into the same place moments ago."""
    if not text or text[0].isspace() or text[0] in ATTACHES:
        return False
    if before is None:
        return follows_last
    if not before:
        return False
    c = before[-1]
    if c.isspace() or c in OPENERS:
        return False
    if c in QUOTES:
        # A straight quote after a word closes it ("said "hi"|"); anywhere else it opens one.
        prev = before[:-1]
        return bool(prev) and not prev.isspace() and prev not in OPENERS
    return True


class LastInsert:
    """Where and when the last dictation went, for when the app can't say what's before the caret."""

    def __init__(self):
        self.window = None
        self.at = -math.inf

    def record(self, window, now: float):
        self.window, self.at = window, now

    def follows(self, window, typed_at: float, now: float) -> bool:
        """Whether the caret is most likely still right after the last dictation: same window,
        not long ago, and no key typed since (which could have moved it)."""
        return (window is not None and window == self.window and now - self.at < FOLLOW_S
                and typed_at < self.at)


class CaretReader:
    """Reads the characters before the caret in the focused app, on its own thread."""

    def __init__(self):
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="murmur-uia")
        self._pending: Future | None = None
        self._uia = None
        # Loads UI Automation now: the first time, comtypes also generates its wrappers (slow).
        self._executor.submit(self._load)

    def start(self) -> Future | None:
        """Starts a read. None if an earlier one is still stuck in some app."""
        if self._pending is not None and not self._pending.done():
            return None
        self._pending = self._executor.submit(self._read)
        return self._pending

    @staticmethod
    def result(read: Future | None, started: float) -> str | None:
        """The read's result, waiting until READ_TIMEOUT_S after it started, or None."""
        if read is None:
            return None
        try:
            return read.result(timeout=max(0.0, started + READ_TIMEOUT_S - time.monotonic()))
        except FutureTimeout:
            log.info("The app took too long to say what's before the caret")
            return None
        except Exception:
            log.warning("Couldn't read what's before the caret", exc_info=True)
            return None

    def _load(self):
        try:
            # UI Automation clients should live in the multithreaded apartment. comtypes joins
            # one when first imported, and this is the thread that imports it.
            sys.coinit_flags = 0  # COINIT_MULTITHREADED
            import comtypes.client
            self._mod = comtypes.client.GetModule("UIAutomationCore.dll")
            self._uia = comtypes.client.CreateObject(self._mod.CUIAutomation, interface=self._mod.IUIAutomation)
        except Exception:
            log.warning("UI Automation is unavailable; spacing falls back to a guess", exc_info=True)

    def _read(self) -> str | None:
        if inserter.foreground_pid() == os.getpid():
            # Murmur's own window would have to answer on the UI thread, which is waiting.
            return None
        focus = inserter.focus_window()
        before = edit_before_caret(focus[1]) if focus else None
        if before is None and self._uia is not None:
            before = before_caret(self._uia, self._mod, self._uia.GetFocusedElement())
        return before


def before_caret(uia, mod, element, count=2) -> str | None:
    """Up to `count` characters before the caret (or the selection, which the text will replace)
    in a UI Automation element; "" at the start of the field; None if it doesn't say."""
    pattern = element.GetCurrentPattern(mod.UIA_TextPatternId)
    if not pattern:
        return None
    rng = None
    selection = pattern.QueryInterface(mod.IUIAutomationTextPattern).GetSelection()
    if selection and selection.Length:
        rng = selection.GetElement(0)
    else:
        # Some apps only report the caret itself (it's at the end of a selection, so second best).
        pattern2 = element.GetCurrentPattern(mod.UIA_TextPattern2Id)
        if pattern2:
            _, rng = pattern2.QueryInterface(mod.IUIAutomationTextPattern2).GetCaretRange()
    if not rng:
        return None
    rng = rng.Clone()
    # Collapse to the start of the caret or selection, then reach back.
    rng.MoveEndpointByRange(mod.TextPatternRangeEndpoint_End, rng, mod.TextPatternRangeEndpoint_Start)
    rng.MoveEndpointByUnit(mod.TextPatternRangeEndpoint_Start, mod.TextUnit_Character, -count)
    return rng.GetText(count + 1)[-count:]


def edit_before_caret(hwnd, count=2) -> str | None:
    """The same for classic Win32 Edit controls, which UI Automation shows without a text pattern."""
    name = ctypes.create_unicode_buffer(32)
    if not hwnd or not user32.GetClassNameW(hwnd, name, 32) or name.value.lower() != "edit":
        return None

    def send(msg, wparam=0, lparam=0) -> int | None:
        result = ctypes.c_size_t()
        if not user32.SendMessageTimeoutW(hwnd, msg, wparam, lparam, SMTO_ABORTIFHUNG, 100, ctypes.byref(result)):
            return None
        return result.value

    # Across processes EM_GETSEL can't fill pointers, but it returns both ends packed in 16 bits.
    length, sel = send(WM_GETTEXTLENGTH), send(EM_GETSEL)
    if length is None or sel is None or length > 0xFFFF:
        return None
    start = sel & 0xFFFF
    buf = ctypes.create_unicode_buffer(start + 1)
    if start and not send(WM_GETTEXT, start + 1, ctypes.addressof(buf)):
        return None
    return buf.value[max(0, start - count):start]

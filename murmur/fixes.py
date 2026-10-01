"""Learning from the user's fixes. After a dictation is pasted, Murmur keeps an eye on that text
for a while; when the user corrects a word it misheard ("Rohid" -> "Rohit"), it's reported to
the app, which learns it (App._learn). learn.py decides what counts as such a fix.

The text is read with UI Automation on spacing.CaretReader's thread (classic Edit controls with
WM_GETTEXT), like the spacing check:
- `start`, right after the paste: the text around the caret, which must end with what was
  pasted, kept as anchors to find it again, and a UI Automation range over it.
- `check`, when the user has typed in that window and paused, and a last one (`finish`) when
  they leave it, start another dictation, or WATCH_S is up: the text around the caret now (the
  fix is usually where the caret is), the range kept at the paste (RichEdit and Notepad move it
  with edits), or the start of the document. learn.find_span picks the pasted text out of it.
A fix counts once two reads in a row agree, or in the last one: a read taken while a word is
being retyped ("Rohi") looks like a fix too.

Tested in Notepad, RichEdit, classic Edit, Qt, Edge and Chrome (textarea and contenteditable),
and VS Code with screen reader support on. VS Code otherwise shows no text, nor do apps run as
administrator, and chat apps clear the box on Enter: then nothing is learned.

The text read stays in memory, on that thread, until the watch ends. Never logged.
"""
import ctypes
import logging
import os
import time
from ctypes import wintypes
from typing import Callable

from . import inserter, learn, spacing

log = logging.getLogger(__name__)

WATCH_S = 120.0  # how long a pasted dictation is watched
IDLE_S = 1.0  # a pause in typing this long before reading
CONTEXT = 60  # characters either side of the pasted text kept to find it again
AROUND = 600  # characters either side of the caret read later
DOC_CAP = 20000  # a document longer than this isn't read from the start
LANDED_TRIES = 4  # reads, PASTE_WAIT_S apart, until the pasted text shows up in the app
PASTE_WAIT_S = 0.15

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.SendMessageTimeoutW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
                                       wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)]
user32.SendMessageTimeoutW.restype = wintypes.LPARAM
WM_GETTEXT, WM_GETTEXTLENGTH, EM_GETSEL = 0x0D, 0x0E, 0xB0
SMTO_ABORTIFHUNG = 0x2


def _nl(text: str) -> str:
    """Line breaks as \\n: RichEdit reports them as \\r, Edit as \\r\\n."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


class _Watch:
    """One pasted dictation being watched. Used on the reading thread only."""

    def __init__(self, inserted: str, window: int):
        self.inserted = _nl(inserted)
        self.window = window
        self.element = None  # the UI Automation element pasted into, or
        self.edit = None  # a classic Edit control's handle
        self.held = None  # a range over the pasted text
        self.before = self.after = ""
        self.seen: set[learn.Fix] = set()  # fixes in the last read
        self.reported: set[tuple[str, str]] = set()


class Watcher:
    """Watches the last pasted dictation. Call from the UI thread; `on_fix(fix)` is called on the
    reading thread."""

    def __init__(self, reader: spacing.CaretReader, on_fix: Callable[[learn.Fix], None]):
        self.reader = reader
        self.on_fix = on_fix
        self.window = None  # where the watched text is, while there is one
        self.started = 0.0
        self.read_at = 0.0  # when the last read was asked for
        self._watch: _Watch | None = None  # touched on the reading thread only
        self._is_word = None

    @property
    def active(self) -> bool:
        return self.window is not None

    def start(self, text: str, window: int):
        """Starts watching `text`, just pasted into `window` (the foreground window)."""
        self.window, self.started = window, time.monotonic()
        self.read_at = self.started
        self.reader.run(lambda uia, mod: self._start(uia, mod, text, window))

    def check(self):
        """Reads the text again and reports fixes two reads in a row agree on."""
        if self.active:
            self.read_at = time.monotonic()
            self.reader.run(lambda uia, mod: self._check(uia, mod, final=False))

    def finish(self):
        """A last read, reporting every fix in it, and the end of the watch."""
        if self.active:
            self.window = None
            self.reader.run(lambda uia, mod: self._check(uia, mod, final=True))

    # On the reading thread.

    def _start(self, uia, mod, text: str, window: int):
        watch = _Watch(text, window)
        self._watch = None
        if inserter.window_pid(window) == os.getpid():
            return  # Murmur's own window answers on the UI thread, which may be waiting on this one
        try:
            focus = inserter.focus_window()
            if not focus or focus[0] != window:
                return
            if _edit_text(focus[1]) is not None:
                watch.edit = focus[1]
                snapshot = self._edit_snapshot
            elif uia is not None:
                watch.element = uia.GetFocusedElement()
                if watch.element is None or watch.element.CurrentIsPassword:
                    return
                snapshot = lambda w: self._uia_snapshot(mod, w)  # noqa: E731
            else:
                return
            for _ in range(LANDED_TRIES):  # the app may still be pasting
                if snapshot(watch):
                    self._watch = watch
                    return
                time.sleep(PASTE_WAIT_S)
            log.info("Couldn't find the pasted text to watch it for fixes")
        except Exception:
            log.info("Couldn't watch the pasted text for fixes", exc_info=True)

    def _check(self, uia, mod, final: bool):
        watch = self._watch
        if watch is None:
            return
        if final:
            self._watch = None
        try:
            t0 = time.perf_counter()
            fixes = self._read_fixes(mod, watch)
            if fixes is None:
                return
            found = set(fixes)
            confirmed = found if final else found & watch.seen
            watch.seen = found
            new = [f for f in fixes if f in confirmed and (f.heard, f.write) not in watch.reported]
            for fix in new:
                watch.reported.add((fix.heard, fix.write))
                self.on_fix(fix)
            log.info("Checked a dictation for fixes in %.0f ms: %d found", (time.perf_counter() - t0) * 1000,
                     len(new))
        except Exception:
            log.info("Couldn't read the text back to look for fixes", exc_info=True)

    def _read_fixes(self, mod, watch: _Watch) -> list[learn.Fix] | None:
        """The fixes in what became of the pasted text, or None if it can't be found."""
        for text in self._reads(mod, watch):
            span = learn.find_span(watch.inserted, watch.before, watch.after, text)
            if span is not None:
                return learn.corrections(watch.inserted, span, self._speller())
        return None

    def _speller(self):
        if self._is_word is None:
            try:
                from .spell import Speller
                self._is_word = Speller().is_word
            except Exception:
                log.warning("Windows' spell checker is unavailable; learning only fixes of phrases",
                            exc_info=True)
                self._is_word = lambda word: True
        return self._is_word

    # Reading, by control.

    def _edit_snapshot(self, watch: _Watch) -> bool:
        got = _edit_text(watch.edit)
        if got is None:
            return False
        text, caret = got
        text, start = _nl(text[:caret]), None
        if text.endswith(watch.inserted.strip()):
            start = len(text) - len(watch.inserted.strip())
        if start is None:
            return False
        watch.before = text[max(0, start - CONTEXT):start]
        watch.after = _nl(got[0][caret:caret + CONTEXT])
        return True

    def _uia_snapshot(self, mod, watch: _Watch) -> bool:
        pattern = _text_pattern(mod, watch.element)
        caret = _caret(mod, watch.element, pattern) if pattern else None
        if caret is None:
            return False
        n = len(watch.inserted)
        before, after = _around(mod, caret, n + CONTEXT, CONTEXT, pattern.DocumentRange)
        pasted = watch.inserted.strip()
        if not before.rstrip().endswith(pasted):
            return False
        before = before.rstrip()
        watch.before, watch.after = before[:len(before) - len(pasted)][-CONTEXT:], after
        held = caret.Clone()
        held.MoveEndpointByUnit(mod.TextPatternRangeEndpoint_Start, mod.TextUnit_Character, -n)
        watch.held = held
        return True

    def _reads(self, mod, watch: _Watch):
        """The text where the pasted text is, read by each way there is, best first."""
        if watch.edit is not None:
            got = _edit_text(watch.edit)
            if got is not None:
                text, caret = got
                yield _nl(text[max(0, caret - AROUND):])
                if len(text) <= DOC_CAP:
                    yield _nl(text)
            return
        pattern = _text_pattern(mod, watch.element)
        if pattern is None:
            return
        doc = pattern.DocumentRange
        caret = _caret(mod, watch.element, pattern)
        if caret is not None:
            yield "".join(_around(mod, caret, AROUND, AROUND, doc))
        if watch.held is not None:
            try:
                before, after = _around(mod, watch.held, CONTEXT, CONTEXT, doc)
                yield before + _nl(watch.held.GetText(DOC_CAP)) + after
            except Exception:
                pass  # the range went with an edit
        yield _nl(doc.GetText(DOC_CAP))


def _text_pattern(mod, element):
    pattern = element.GetCurrentPattern(mod.UIA_TextPatternId)
    return pattern.QueryInterface(mod.IUIAutomationTextPattern) if pattern else None


def _caret(mod, element, pattern):
    """An empty range at the caret (the end of the selection, where a paste leaves it)."""
    selection = pattern.GetSelection()
    if selection and selection.Length:
        rng = selection.GetElement(0).Clone()
        rng.MoveEndpointByRange(mod.TextPatternRangeEndpoint_Start, rng, mod.TextPatternRangeEndpoint_End)
        return rng
    pattern2 = element.GetCurrentPattern(mod.UIA_TextPattern2Id)
    if pattern2:
        _, rng = pattern2.QueryInterface(mod.IUIAutomationTextPattern2).GetCaretRange()
        return rng
    return None


def _around(mod, rng, before: int, after: int, doc) -> tuple[str, str]:
    """Up to `before` characters before the range and `after` after it, within the document:
    Chromium's <textarea> lets a range move past the end of the text, into stale copies of text
    since replaced."""
    start, end = mod.TextPatternRangeEndpoint_Start, mod.TextPatternRangeEndpoint_End
    b = rng.Clone()
    b.MoveEndpointByRange(end, b, start)
    b.MoveEndpointByUnit(start, mod.TextUnit_Character, -before)
    a = rng.Clone()
    a.MoveEndpointByRange(start, a, end)
    a.MoveEndpointByUnit(end, mod.TextUnit_Character, after)
    if b.CompareEndpoints(start, doc, start) < 0:
        b.MoveEndpointByRange(start, doc, start)
    if a.CompareEndpoints(end, doc, end) > 0:
        a.MoveEndpointByRange(end, doc, end)
    return _nl(b.GetText(before + 1)), _nl(a.GetText(after + 1))


def _edit_text(hwnd) -> tuple[str, int] | None:
    """A classic Edit control's text up to AROUND characters past the caret, and the caret's
    position. None past 64K characters, where EM_GETSEL can't say where the caret is."""
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
    caret = (sel >> 16) & 0xFFFF
    n = min(length, caret + AROUND)
    buf = ctypes.create_unicode_buffer(n + 1)
    if n and not send(WM_GETTEXT, n + 1, ctypes.addressof(buf)):
        return None
    return buf.value, caret

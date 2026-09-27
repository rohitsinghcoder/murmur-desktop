import time
from concurrent.futures import Future, ThreadPoolExecutor

import pytest

from murmur import spacing
from murmur.spacing import LastInsert, needs_space


@pytest.mark.parametrize("before, space", [
    ("e.", True),  # "Hello there.|" -> "Hello there. How"
    ("lo", True),
    ("", False),  # empty field, or the caret at its start
    (". ", False),
    ("\r\n", False),
    ("e\r", False),
    ("\t", False),
    ("x(", False),
    (" “", False),
    ("¿", False),
    ("a/", False),
    (' "', False),  # opening quote
    ('"', False),  # a quote at the start of the field opens
    ('s"', True),  # closing quote: 'said "yes"|'
    ("s'", True),
    ("(\"", False),
])
def test_space_depends_on_what_is_before_the_caret(before, space):
    assert needs_space("How are you?", before) is space


@pytest.mark.parametrize("text", [", and then", ". Done", "?", ")", "…", "% more", " already spaced", ""])
def test_no_space_before_text_that_attaches_or_is_already_spaced(text):
    assert not needs_space(text, "d", follows_last=True)


def test_unknown_caret_falls_back_to_following_the_last_dictation():
    assert needs_space("How", None, follows_last=True)
    assert not needs_space("How", None, follows_last=False)
    # When the app does say, that wins over the guess.
    assert not needs_space("How", " ", follows_last=True)
    assert needs_space("How", "e.", follows_last=False)


def test_last_insert_follows_only_same_window_soon_without_typing():
    last = LastInsert()
    assert not last.follows((1, 2), typed_at=0.0, now=10.0)  # nothing dictated yet
    last.record((1, 2), now=100.0)
    assert last.follows((1, 2), typed_at=50.0, now=110.0)
    assert not last.follows((1, 3), typed_at=50.0, now=110.0)  # another field
    assert not last.follows((9, 2), typed_at=50.0, now=110.0)  # another window
    assert not last.follows((1, 2), typed_at=105.0, now=110.0)  # typed since: the caret may have moved
    assert not last.follows((1, 2), typed_at=50.0, now=100.0 + spacing.FOLLOW_S)  # too long ago
    assert not last.follows(None, typed_at=50.0, now=110.0)


@pytest.fixture
def edit():
    """A classic Win32 Edit control (never shown). Returns set(text, sel_start, sel_end) -> hwnd."""
    import ctypes
    from ctypes import wintypes
    u = ctypes.WinDLL("user32")
    u.CreateWindowExW.restype = wintypes.HWND
    u.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                  ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                  wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
    u.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    u.SetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPCWSTR]
    u.DestroyWindow.argtypes = [wintypes.HWND]
    hwnd = u.CreateWindowExW(0, "EDIT", None, 0x4, 0, 0, 200, 50, None, None, None, None)  # ES_MULTILINE

    def set_text(text, start, end):
        u.SetWindowTextW(hwnd, text)
        u.SendMessageW(hwnd, 0xB1, start, end)  # EM_SETSEL
        return hwnd

    yield set_text
    u.DestroyWindow(hwnd)


def test_reads_classic_edit_controls(edit):
    assert spacing.edit_before_caret(edit("Hello there.", 12, 12)) == "e."
    assert spacing.edit_before_caret(edit("", 0, 0)) == ""
    assert spacing.edit_before_caret(edit("abc def", 4, 7)) == "c "  # before the selection
    assert spacing.edit_before_caret(edit("x", 1, 1)) == "x"
    assert spacing.edit_before_caret(None) is None


def test_slow_app_times_out_instead_of_holding_up_the_text():
    with ThreadPoolExecutor(1) as ex:
        read = ex.submit(time.sleep, spacing.READ_TIMEOUT_S + 0.15)
        t0 = time.monotonic()
        assert spacing.CaretReader.result(read, t0) is None
        assert time.monotonic() - t0 < spacing.READ_TIMEOUT_S + 0.1


def test_failed_or_missing_read_means_unknown():
    failed = Future()
    failed.set_exception(OSError("COM error"))
    assert spacing.CaretReader.result(failed, time.monotonic()) is None
    assert spacing.CaretReader.result(None, time.monotonic()) is None
    done = Future()
    done.set_result("e.")
    assert spacing.CaretReader.result(done, time.monotonic() - 10) == "e."  # already there: no wait

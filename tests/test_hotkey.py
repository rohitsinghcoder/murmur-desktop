import time

import pytest

from murmur import hotkey

RCTRL, ESC, KEY_C = hotkey.VK_RCONTROL, hotkey.VK_ESCAPE, 0x43


@pytest.fixture
def keys(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(hotkey.time, "monotonic", lambda: now[0])
    events = []
    k = hotkey.HoldToTalk(
        on_start=lambda: events.append("start"), on_finish=lambda: events.append("finish"),
        on_cancel=lambda: events.append("cancel"), on_lock=lambda: events.append("lock"),
    )
    k.events, k.now = events, now
    return k


def wait(k, secs):
    k.now[0] += secs


def test_hold_then_release_finishes(keys):
    keys._on_key(RCTRL, True)
    wait(keys, 0.1)
    keys._on_key(RCTRL, True)  # auto-repeat is ignored
    wait(keys, 1.5)
    keys._on_key(RCTRL, False)
    assert keys.events == ["start", "finish"]


def test_single_tap_cancels(keys):
    keys._on_key(RCTRL, True)
    wait(keys, 0.1)
    keys._on_key(RCTRL, False)
    time.sleep(hotkey.DOUBLE_TAP_S + 0.1)  # real timer
    assert keys.events == ["start", "cancel"]


def test_double_tap_locks_then_tap_finishes(keys):
    keys._on_key(RCTRL, True)
    wait(keys, 0.1)
    keys._on_key(RCTRL, False)
    keys._on_key(RCTRL, True)
    keys._on_key(RCTRL, False)
    assert keys.events == ["start", "lock"]
    wait(keys, 5)
    keys._on_key(KEY_C, True)  # typing while hands-free doesn't stop it
    keys._on_key(RCTRL, True)
    assert keys.events == ["start", "lock"]  # finishes on release, not press
    keys._on_key(RCTRL, False)
    assert keys.events == ["start", "lock", "finish"]


def test_shortcut_while_holding_cancels(keys):
    keys._on_key(RCTRL, True)
    assert keys._on_key(KEY_C, True) is False  # the shortcut still reaches the app
    wait(keys, 1)
    keys._on_key(RCTRL, False)
    assert keys.events == ["start", "cancel"]


def test_escape_cancels_and_is_swallowed(keys):
    keys._on_key(RCTRL, True)
    assert keys._on_key(ESC, True) is True
    keys._on_key(RCTRL, False)
    assert keys.events == ["start", "cancel"]


def test_escape_when_idle_passes_through(keys):
    assert keys._on_key(ESC, True) is False
    assert keys.events == []

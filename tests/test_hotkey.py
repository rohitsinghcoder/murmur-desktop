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


def test_typing_is_noticed_but_the_hotkey_is_not(keys):
    keys._on_key(KEY_C, True)
    keys._on_key(KEY_C, False)
    assert keys.typed_at == 100.0
    wait(keys, 5)
    keys._on_key(RCTRL, True)
    wait(keys, 1)
    keys._on_key(RCTRL, False)
    assert keys.typed_at == 100.0  # dictating doesn't count as typing


def test_escape_when_idle_passes_through(keys):
    assert keys._on_key(ESC, True) is False
    assert keys.events == []


CTRL_L, CTRL_R, SHIFT_L, SPACE, WIN_L, F9 = 0xA2, 0xA3, 0xA0, 0x20, 0x5B, 0x78


def test_combo_needs_all_keys_and_swallows_the_trigger_key(keys, monkeypatch):
    keys.set_hotkey(["ctrl", "shift", "vk_20"])
    assert keys._on_key(CTRL_L, True) is False  # modifiers reach the app
    assert keys._on_key(SHIFT_L, True) is False
    assert keys.events == []
    assert keys._on_key(SPACE, True) is True  # Space doesn't type into the app
    assert keys.events == ["start"]
    wait(keys, 1)
    assert keys._on_key(SPACE, False) is True
    assert keys.events == ["start", "finish"]
    keys._on_key(SHIFT_L, False)
    keys._on_key(CTRL_L, False)
    assert keys.events == ["start", "finish"]


def test_space_alone_still_types_with_combo_hotkey(keys):
    keys.set_hotkey(["ctrl", "shift", "vk_20"])
    assert keys._on_key(SPACE, True) is False
    assert keys._on_key(SPACE, False) is False
    assert keys.events == []


def test_generic_modifier_matches_either_side(keys):
    keys.set_hotkey(["ctrl", "vk_20"])
    keys._on_key(CTRL_R, True)
    keys._on_key(SPACE, True)
    assert keys.events == ["start"]


def test_win_combo_presses_dummy_key(keys, monkeypatch):
    tapped = []
    monkeypatch.setattr(hotkey.inserter, "tap", tapped.append)
    keys.set_hotkey(["ctrl", "win"])
    keys._on_key(CTRL_L, True)
    keys._on_key(WIN_L, True)
    assert keys.events == ["start"] and tapped == [hotkey.VK_DUMMY]


def test_recording_captures_combo_and_blocks_keys(keys):
    got = []
    keys.record(got.append)
    assert keys._on_key(CTRL_L, True) is True
    assert keys._on_key(SHIFT_L, True) is True
    assert keys._on_key(SPACE, True) is True
    keys._on_key(SPACE, False)
    keys._on_key(SHIFT_L, False)
    assert got == []
    keys._on_key(CTRL_L, False)
    assert got == [[CTRL_L, SHIFT_L, SPACE]]
    assert keys.events == []  # recording never starts dictation
    assert hotkey.from_pressed(got[0]) == ["ctrl", "shift", "vk_20"]


def test_recording_escape_cancels(keys):
    got = []
    keys.record(got.append)
    keys._on_key(ESC, True)
    assert got == [None]
    keys._on_key(RCTRL, True)
    assert keys.events == ["start"]  # back to normal


@pytest.mark.parametrize("pressed, names, label", [
    ([CTRL_R], ["rctrl"], "Right Ctrl"),
    ([F9], ["vk_78"], "F9"),
    ([CTRL_L, WIN_L], ["ctrl", "win"], "Ctrl + Win"),
    ([SHIFT_L, CTRL_R, SPACE], ["ctrl", "shift", "vk_20"], "Ctrl + Shift + Space"),
])
def test_from_pressed_and_describe(pressed, names, label):
    assert hotkey.from_pressed(pressed) == names
    assert hotkey.describe(names) == label
    assert hotkey.problem(names) is None


@pytest.mark.parametrize("names", [["vk_41"], ["vk_20"], ["shift", "vk_41"], ["vk_1b"], ["ctrl", "vk_1b"]])
def test_problem_rejects_typing_keys(names):
    assert hotkey.problem(names)

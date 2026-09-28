import json
import time

import pytest

from murmur import history


@pytest.fixture
def store(tmp_path, monkeypatch):
    """History in a temporary folder."""
    monkeypatch.setattr(history, "DIR", tmp_path)
    monkeypatch.setattr(history, "FILE", tmp_path / "history.jsonl")
    monkeypatch.setattr(history, "_OLD_FILE", tmp_path / "old" / "history.jsonl")
    monkeypatch.setattr(history, "keep", "forever")
    return tmp_path


def write(entries):
    history.FILE.write_text("".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")


def entry(text, audio_ms=6000, app="chrome.exe", days_ago=0.0):
    return {"time": int((time.time() - days_ago * 86400) * 1000), "text": text, "audioMs": audio_ms, "app": app}


def test_add_and_delete(store):
    history.add("Hello there.", 1500, "notepad.exe")
    history.add("Second one.", 1200, "chrome.exe")
    entries = history.load()
    assert [e["text"] for e in entries] == ["Second one.", "Hello there."]
    history.delete(entries[0]["time"])
    assert [e["text"] for e in history.load()] == ["Hello there."]


def test_entries_saved_in_the_same_millisecond_get_their_own_ids(store, monkeypatch):
    monkeypatch.setattr(history.time, "time", lambda: 1_700_000_000.0)
    history.add("One.", 1000, "notepad.exe")
    history.add("Two.", 1000, "notepad.exe")
    first, second = history.load()
    assert first["time"] != second["time"]
    history.delete(first["time"])
    assert [e["text"] for e in history.load()] == ["One."]


def test_try_it_box_is_not_saved(store):
    history.add("Just testing.", 1000, history.TRY_IT)
    history.add("\n", 1000, "notepad.exe")  # "new line" on its own: typed, but nothing to keep
    assert history.load() == []


def test_older_try_it_entries_are_left_out(store):
    lines = [entry("Real one."), entry("Practice.", app=history.TRY_IT)]
    history.FILE.write_text("".join(json.dumps(e) + "\n" for e in lines), encoding="utf-8")
    assert [e["text"] for e in history.load()] == ["Real one."]


def test_stats_skip_try_it_entries():
    s = history.stats([entry("one two three"), entry("four five", app=history.TRY_IT)])
    assert s["words"] == 3 and s["dictations"] == 1


def test_time_saved_against_typing():
    # 300 words spoken in 2 minutes is 150 wpm: typing them at 40 wpm takes 7.5 minutes.
    s = history.stats([entry(" ".join(["word"] * 150), audio_ms=60000)] * 2)
    assert s["wpm"] == 150
    assert s["timesFaster"] == 3.8
    assert s["minutesSaved"] == 6  # 7.5 - 2 = 5.5, rounded to even


def test_time_saved_never_negative():
    s = history.stats([entry("one two three", audio_ms=600000)])
    assert s["timesFaster"] == 0.0 and s["minutesSaved"] == 0


def test_keep_prunes_old_dictations(store):
    write([entry("Two years ago.", days_ago=730), entry("Last month.", days_ago=40), entry("Today.")])
    history.prune()
    assert len(history.load()) == 3  # forever
    history.keep = "year"
    history.prune()
    assert [e["text"] for e in history.load()] == ["Today.", "Last month."]
    history.keep = "month"
    history.add("Just now.", 1000, "notepad.exe")  # adding prunes too
    assert [e["text"] for e in history.load()] == ["Just now.", "Today."]


def test_keep_off_saves_nothing_new(store):
    write([entry("Kept.")])
    history.keep = "off"
    history.add("Not saved.", 1000, "notepad.exe")
    history.prune()
    assert [e["text"] for e in history.load()] == ["Kept."]


def test_clear(store):
    history.add("Something.", 1000, "notepad.exe")
    history.clear()
    assert history.load() == []
    history.clear()  # nothing to clear is fine


@pytest.mark.parametrize("name", ["out.md", "out.txt"])
def test_export(store, name):
    write([entry("First.", days_ago=1), entry("Dear team,\nIt's out.")])
    path = store / name
    assert history.export(path) == 2
    text = path.read_text(encoding="utf-8")
    assert text.index("First.") < text.index("Dear team,")
    if name.endswith(".md"):
        assert text.startswith("# Murmur history") and "Dear team,  \nIt's out." in text
    else:
        assert "#" not in text and "It's out." in text


def test_no_speech_no_stats():
    s = history.stats([])
    assert s == {"words": 0, "wpm": 0, "dictations": 0, "streak": 0, "timesFaster": 0, "minutesSaved": 0}

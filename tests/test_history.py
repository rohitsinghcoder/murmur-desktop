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
    return tmp_path


def entry(text, audio_ms=6000, app="chrome.exe", days_ago=0.0):
    return {"time": int((time.time() - days_ago * 86400) * 1000), "text": text, "audioMs": audio_ms, "app": app}


def test_add_and_delete(store):
    history.add("Hello there.", 1500, "notepad.exe")
    history.add("Second one.", 1200, "chrome.exe")
    entries = history.load()
    assert [e["text"] for e in entries] == ["Second one.", "Hello there."]
    history.delete(entries[0]["time"])
    assert [e["text"] for e in history.load()] == ["Hello there."]


def test_try_it_box_is_not_saved(store):
    history.add("Just testing.", 1000, history.TRY_IT)
    assert history.load() == []


def test_older_try_it_entries_are_left_out(store):
    lines = [entry("Real one."), entry("Practice.", app=history.TRY_IT)]
    history.FILE.write_text("".join(json.dumps(e) + "\n" for e in lines), encoding="utf-8")
    assert [e["text"] for e in history.load()] == ["Real one."]


def test_stats_skip_try_it_entries():
    s = history.stats([entry("one two three"), entry("four five", app=history.TRY_IT)])
    assert s["words"] == 3 and s["dictations"] == 1

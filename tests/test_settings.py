import json

import pytest

from murmur import history, settings


@pytest.fixture
def folder(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DIR", tmp_path)
    monkeypatch.setattr(settings, "FILE", tmp_path / "settings.json")
    monkeypatch.setattr(history, "FILE", tmp_path / "history.jsonl")
    return tmp_path


def test_defaults_on_first_run(folder):
    s = settings.load()
    assert s == {**settings.DEFAULTS, "onboarded": False}


def test_existing_users_skip_the_checklist(folder):
    history.FILE.write_text("{}\n", encoding="utf-8")
    settings.FILE.write_text(json.dumps({"hotkey": ["f9"]}), encoding="utf-8")
    s = settings.load()
    assert s["onboarded"] is True and s["hotkey"] == ["f9"]


def test_bad_values_are_dropped(folder):
    settings.FILE.write_text(json.dumps({"digits": "yes", "keep_history": "decade", "unknown": 1}), encoding="utf-8")
    s = settings.load()
    assert s["digits"] is True and s["keep_history"] == "forever" and "unknown" not in s


def test_round_trip(folder):
    s = settings.load()
    s["dictionary"] = [["rohit", "Rohit"]]
    settings.save(s)
    assert settings.load()["dictionary"] == [["rohit", "Rohit"]]

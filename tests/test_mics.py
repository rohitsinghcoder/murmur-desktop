import pytest

from murmur import mics

# What PortAudio lists on a typical laptop: MME (0) cuts names at 31 characters, DirectSound (1)
# and WASAPI (2) list the same devices in full.
DEVICES = [
    {"name": "Microsoft Sound Mapper - Input", "hostapi": 0, "max_input_channels": 2},
    {"name": "Microphone Array (Realtek(R) Au", "hostapi": 0, "max_input_channels": 2},
    {"name": "Microphone (USB Mic)", "hostapi": 0, "max_input_channels": 1},
    {"name": "Speakers (Realtek(R) Audio)", "hostapi": 0, "max_input_channels": 0},
    {"name": "Primary Sound Capture Driver", "hostapi": 1, "max_input_channels": 2},
    {"name": "Microphone Array (Realtek(R) Audio)", "hostapi": 1, "max_input_channels": 2},
    {"name": "Microphone Array (Realtek(R) Audio)", "hostapi": 2, "max_input_channels": 2},
]


@pytest.fixture
def devices(monkeypatch):
    monkeypatch.setattr(mics.sd, "query_devices", lambda *a, **k: DEVICES)
    monkeypatch.setattr(mics.sd.default, "device", [1, 3])


def test_inputs_are_real_mics_with_full_names(devices):
    assert mics.inputs() == [{"index": 1, "name": "Microphone Array (Realtek(R) Audio)"},
                             {"index": 2, "name": "Microphone (USB Mic)"}]


def test_find_by_name(devices):
    assert mics.find("Microphone (USB Mic)") == 2
    assert mics.find("Microphone Array (Realtek(R) Audio)") == 1


def test_missing_mic_falls_back_to_default(devices):
    assert mics.find("Headset (Bluetooth)") is None
    assert mics.find("") is None

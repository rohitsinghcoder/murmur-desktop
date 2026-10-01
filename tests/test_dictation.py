import threading
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest

from murmur import dictation
from murmur.dictation import SR, Session

FRAME = SR // 20  # 50 ms, like the mic
WORD_S = 0.25


def words(seconds):
    return int(round(seconds / WORD_S))


def speech(secs):
    """Words: 0.2 s of tone (about -23 dB), then a 0.05 s gap."""
    word = np.concatenate([0.1 * np.sin(2 * np.pi * 220 * np.arange(int(0.2 * SR)) / SR),
                           np.zeros(int(0.05 * SR))]).astype(np.float32)
    return np.tile(word, words(secs))


def quiet(secs):
    return np.zeros(int(secs * SR), np.float32)


@pytest.fixture
def run():
    """Feeds audio to a Session frame by frame. The fake model hears a word wherever a tone
    starts, reported at that time, and records how much audio each call got."""
    calls = []

    def decode(audio):
        calls.append(len(audio) / SR)
        step = SR // 100  # 10 ms
        loud = [np.abs(audio[i:i + step]).max() > 0.001 for i in range(0, len(audio), step)]
        return [(" w", i * step / SR) for i, on in enumerate(loud) if on and (i == 0 or not loud[i - 1])]

    ex = ThreadPoolExecutor(max_workers=1)
    session = Session(decode, ex)

    def feed(*parts):
        audio = np.concatenate(parts)
        for i in range(0, len(audio), FRAME):
            session.add(audio[i:i + FRAME])
            # Let background work (guesses and finished pieces) finish, like real time would;
            # otherwise a piece may still be decoding when the test looks at `calls`.
            for f in session.pieces + ([session.guess[1]] if session.guess else []):
                f.result()
        return session

    yield feed, calls
    ex.shutdown()


def test_short_dictation_is_one_transcription(run):
    feed, calls = run
    s = feed(speech(3))
    assert s.text().split() == ["w"] * words(3)
    assert calls == [pytest.approx(3.0)]


def test_pause_before_stopping_uses_background_result(run):
    feed, calls = run
    s = feed(speech(2), quiet(0.5))
    assert len(calls) == 1
    assert s.text().split() == ["w"] * words(2)
    assert len(calls) == 1  # nothing left to do after stopping


def test_speaking_after_the_pause_transcribes_again(run):
    feed, calls = run
    s = feed(speech(2), quiet(0.5), speech(1))
    assert s.text().split() == ["w"] * words(3)
    assert calls[-1] == pytest.approx(3.5)


def test_long_dictation_is_finished_in_pieces_without_losing_or_repeating_words(run):
    feed, calls = run
    s = feed(speech(6), quiet(0.5), speech(6), quiet(0.5), speech(4))
    assert len(s.pieces) == 2
    assert s.text().split() == ["w"] * words(16)
    # After stopping, only the open tail (plus context) is transcribed, not all 17 seconds.
    assert calls[-1] < 7


def test_pieces_hear_context_either_side_of_the_cut(run):
    feed, calls = run
    s = feed(speech(6), quiet(0.5), speech(3))
    cut = s.done_until / SR
    assert 6.0 < cut < 6.5  # inside the pause
    # The piece was transcribed with audio past the cut, and the rest starts before it.
    assert any(c == pytest.approx(cut + dictation.LOOKAHEAD_S, abs=0.06) for c in calls)
    assert s.text().split() == ["w"] * words(9)
    assert calls[-1] == pytest.approx(9.5 - (cut - dictation.CONTEXT_S), abs=0.1)


def test_no_pause_is_cut_at_the_maximum(run):
    feed, calls = run
    s = feed(speech(dictation.MAX_OPEN_S + 3))
    assert len(s.pieces) == 1
    assert len(s.text().split()) == pytest.approx(words(dictation.MAX_OPEN_S + 3), abs=1)


def test_quiet_microphone_is_still_transcribed_and_never_cut_at_pauses(run):
    feed, calls = run
    s = feed(speech(8) * 0.02)  # below the voice threshold throughout
    assert s.guess is None and not s.pieces
    s.text()
    assert calls == [pytest.approx(8.0)]


def room(secs, db=-55.0):
    """Mic noise in a quiet room: well below speech, well above digital silence."""
    rng = np.random.default_rng(0)
    return (rng.standard_normal(int(secs * SR)) * 10 ** (db / 20)).astype(np.float32)


def test_digital_silence_is_told_apart_from_a_quiet_room(run):
    feed, calls = run
    assert feed(quiet(2)).silent
    assert not Session(None, None).silent  # nothing recorded yet


def test_quiet_room_and_short_silence_are_not_silent(run):
    feed, calls = run
    assert not feed(room(2)).silent
    s = Session(None, None)
    for _ in range(10):
        s.add(quiet(0.05))
    assert not s.silent  # too short to judge


def fake_decode(audio):
    """Like the fake model in `run` (a word wherever a tone starts), deaf to room noise."""
    step = SR // 100
    loud = [np.abs(audio[i:i + step]).max() > 0.05 for i in range(0, len(audio), step)]
    return [(" w", i * step / SR) for i, on in enumerate(loud) if on and (i == 0 or not loud[i - 1])]


class FakeMic:
    """Stands in for sd.InputStream: plays `audio` into the callback as fast as it's taken, and
    more with play()."""

    def __init__(self, audio):
        self.audio = audio
        self.played = threading.Event()
        self.active = False
        self.opened = 0

    def __call__(self, samplerate, channels, dtype, blocksize, device, callback):
        self.opened += 1
        self.blocksize, self.callback = blocksize, callback
        return self

    def start(self):
        self.active = True
        self.play(self.audio)

    def play(self, audio):
        self.played.clear()

        def run():
            for i in range(0, len(audio), self.blocksize):
                if not self.active:
                    break
                block = audio[i:i + self.blocksize]
                self.callback(block.reshape(-1, 1), len(block), None, None)
            self.played.set()

        threading.Thread(target=run, daemon=True).start()

    def stop(self):
        self.active = False

    def close(self):
        pass


@pytest.fixture
def mic(monkeypatch):
    """A Dictation on a fake mic and model: (dictation, results, play(audio) -> FakeMic)."""
    monkeypatch.setattr(dictation.engine, "tokens", lambda rec, audio, vocab=None: fake_decode(audio))
    results = {}
    ended = threading.Event()

    def end(kind, *args):
        results[kind] = args
        ended.set()

    d = dictation.Dictation(
        None, on_done=lambda *a: end("done", *a), on_error=lambda *a: end("error", *a),
        on_silent=lambda: end("silent"),
    )
    d.ended = ended

    def play(audio) -> FakeMic:
        fake = FakeMic(audio)
        monkeypatch.setattr(dictation.sd, "InputStream", fake)
        return fake

    yield d, results, play
    d.close()
    d.executor.shutdown()


def test_silent_microphone_is_reported_instead_of_transcribed(mic):
    d, results, play = mic
    fake = play(quiet(2))
    d.listen()
    assert fake.played.wait(5)
    d.finish()
    assert d.ended.wait(5)
    assert list(results) == ["silent"]


def test_quiet_room_is_transcribed_as_usual(mic):
    d, results, play = mic
    fake = play(np.concatenate([room(0.5), speech(1) + room(1), room(0.5)]))
    d.listen()
    assert fake.played.wait(5)
    d.finish()
    assert d.ended.wait(5)
    text, audio_ms, _ = results["done"]
    assert text and audio_ms == 2000


def test_hands_free_finishes_by_itself_after_a_minute_without_speech(mic):
    d, results, play = mic
    stopped = threading.Event()
    d.on_auto_stop = stopped.set
    idle = dictation.HANDS_FREE_IDLE_S
    play(np.concatenate([speech(2), room(idle + 5)]))
    d.listen(hands_free=True)
    assert stopped.wait(10)  # nobody called finish()
    assert d.ended.wait(5)
    text, audio_ms, _ = results["done"]
    assert text  # delivered, not thrown away
    assert audio_ms >= (2 + idle) * 1000


def test_hands_free_keeps_listening_while_there_is_speech(mic):
    d, results, play = mic
    stopped = threading.Event()
    d.on_auto_stop = stopped.set
    gap = dictation.HANDS_FREE_IDLE_S - 10
    fake = play(np.concatenate([speech(1), room(gap), speech(1), room(gap)]))
    d.listen(hands_free=True)
    assert fake.played.wait(10)
    assert not d.ended.wait(0.3) and not stopped.is_set()
    d.finish()
    assert d.ended.wait(5) and "done" in results


def dictate(d, results, fake, audio=None):
    """One dictation: plays `audio` (or what the fake mic starts with), stops, waits for the end."""
    d.ended.clear()
    results.clear()
    d.listen()
    if audio is not None:
        deadline = time.monotonic() + 5
        while d._chunks is None and time.monotonic() < deadline:  # until it takes audio
            time.sleep(0.001)
        fake.play(audio)
    assert fake.played.wait(5)
    d.finish()
    assert d.ended.wait(5)


def test_back_to_back_dictations_reuse_the_open_mic_and_ignore_audio_between(mic):
    d, results, play = mic
    fake = play(speech(1))
    dictate(d, results, fake)
    assert results["done"][1] == 1000
    fake.play(speech(3))  # said between dictations: dropped
    assert fake.played.wait(5)
    dictate(d, results, fake, speech(2))
    assert fake.opened == 1 and fake.active
    assert results["done"][1] == 2000


def test_mic_closes_after_the_grace_period(mic, monkeypatch):
    monkeypatch.setattr(dictation, "MIC_KEEP_OPEN_S", 0.1)
    d, results, play = mic
    fake = play(speech(1))
    dictate(d, results, fake)
    time.sleep(0.3)
    assert not fake.active and d._stream is None
    fake = play(speech(1))
    dictate(d, results, fake)  # opens a new one
    assert fake.opened == 1 and "done" in results


def test_holding_the_hotkey_never_finishes_by_itself(mic):
    d, results, play = mic
    stopped = threading.Event()
    d.on_auto_stop = stopped.set
    fake = play(np.concatenate([speech(1), room(dictation.HANDS_FREE_IDLE_S + 5)]))
    d.listen()
    assert fake.played.wait(10)
    assert not d.ended.wait(0.3) and not stopped.is_set()
    d.cancel()


def test_cut_pause_shortens_as_the_open_stretch_grows():
    assert dictation.cut_pause(dictation.CUT_AFTER_S) == pytest.approx(dictation.CUT_PAUSE_S)
    middle = dictation.cut_pause(dictation.CUT_AFTER_S + dictation.CUT_SHORTEN_S / 2)
    assert dictation.CUT_PAUSE_MIN_S < middle < dictation.CUT_PAUSE_S
    assert dictation.cut_pause(dictation.MAX_OPEN_S) == pytest.approx(dictation.CUT_PAUSE_MIN_S)


@pytest.mark.parametrize("pieces, text", [
    ([" observed Phebe,", ", turning away."], " observed Phebe, turning away."),
    ([" It is done.", ". Next one."], " It is done. Next one."),
    ([" Hello,", " world."], " Hello, world."),
    ([" Wait", ", what?"], " Wait, what?"),  # a comma only after the cut is kept
])
def test_pieces_join_without_doubled_punctuation(pieces, text):
    assert dictation.join(pieces) == text


def test_an_unloaded_model_loads_again_when_needed(monkeypatch):
    loads = []
    monkeypatch.setattr(dictation.engine, "load", lambda: loads.append(1) or "model")
    monkeypatch.setattr(dictation.engine, "transcribe", lambda rec, audio, vocab=None: f"{rec} heard {len(audio)}")
    monkeypatch.setattr(dictation.engine, "unload", lambda: None)
    d = dictation.Dictation("model")
    assert d.transcribe(np.zeros(10, np.float32)) == "model heard 10" and not loads
    d.unload()
    d.executor.submit(lambda: None).result()  # unloading is queued on the decode thread
    assert not d.loaded
    assert d.transcribe(np.zeros(10, np.float32)) == "model heard 10"
    assert loads == [1] and d.loaded

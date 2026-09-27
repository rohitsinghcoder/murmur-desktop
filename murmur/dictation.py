"""Records from the microphone and turns it into text.

The model transcribes whole stretches of audio, so to keep the wait after you stop short:
- at every short pause, what you've said so far is transcribed in the background. If you stop
  after such a pause (the usual case), that result is used and the text appears right away;
- long dictations are finished piece by piece while you keep talking, cut at natural pauses.
  Each piece is transcribed with a couple of seconds of audio either side of it, and only the
  words heard inside the piece are kept (the model reports when it heard each word). The model
  so always hears a sentence around the cut, and a pause mid-sentence doesn't turn into a full
  stop and a capital letter.

The mic is read on its own (audio callback) thread and queued, so a slow step never makes the
recorder drop audio.
"""
import logging
import math
import queue
import threading
import time
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable

import numpy as np
import sounddevice as sd

from . import cleanup, engine

log = logging.getLogger(__name__)
SR = engine.SAMPLE_RATE
# Audio kept after the stop, for a word still being finished.
TAIL_S = 0.2
BLOCK = SR // 20  # 50 ms
# Frames louder than this count as speech. Room noise on a laptop mic is around -52 dB.
VOICE_DB = -45.0
# Transcribe in the background after this much quiet following speech.
SPECULATE_AFTER_S = 0.3
# Once this much speech is unfinished, finish it at the next pause of CUT_PAUSE_S...
CUT_AFTER_S = 5.0
CUT_PAUSE_S = 0.35
# ...or anyway at this length.
MAX_OPEN_S = 30.0
# Audio either side of a piece that the model hears for context, without keeping its words.
CONTEXT_S = 2.0
LOOKAHEAD_S = 1.5
# A muted mic, or one blocked in Windows' privacy settings, records digital silence: exact
# zeros, or dither far below any real mic's own noise (a quiet room is still about -52 dB).
SILENT_DB = -80.0
# Judged only on dictations at least this long; a stream can start with a few empty blocks.
SILENT_MIN_S = 1.0


def db(chunk: np.ndarray) -> float:
    rms = math.sqrt(float(np.mean(chunk * chunk))) if len(chunk) else 0.0
    return 20 * math.log10(rms + 1e-6)


def level(chunk: np.ndarray) -> float:
    """Loudness of a chunk mapped to 0..1: room noise (about -52 dB on a laptop mic) stays at 0,
    quiet speech (-40 dB) is about 0.3, and loud speech (-20 dB) fills it."""
    return min(1.0, max(0.0, (db(chunk) + 50) / 30))


Tokens = list[tuple[str, float]]


class Session:
    """The audio of one dictation, and the background transcription of it.

    `decode` turns audio into text pieces with the time each was heard (engine.tokens).
    """

    def __init__(self, decode: Callable[[np.ndarray], Tokens], executor: ThreadPoolExecutor):
        self.decode = decode
        self.executor = executor
        self.frames: list[np.ndarray] = []
        self.samples = 0
        self.done_until = 0  # samples before this are in `pieces`
        self.last_voice = -1  # end of the last loud frame, in samples
        self.quiet = 0  # samples of quiet at the end
        self.cut_at: int | None = None  # a pause where the next piece will end
        self.pieces: list[Future] = []  # finished pieces' text, in order
        self.guess: tuple[int, Future] | None = None  # (samples covered, text of the rest)
        self.loudest = -math.inf  # dB of the loudest frame

    @property
    def silent(self) -> bool:
        """The mic gave nothing but digital silence (muted or blocked), not just a quiet room."""
        return self.samples >= SILENT_MIN_S * SR and self.loudest < SILENT_DB

    def _audio(self) -> np.ndarray:
        if len(self.frames) > 1:
            self.frames = [np.concatenate(self.frames)]
        return self.frames[0] if self.frames else np.zeros(0, np.float32)

    def _transcribe(self, keep_to: float) -> Future:
        """Text heard between `done_until` and `keep_to` (samples), transcribed with context."""
        start = max(0, self.done_until - int(CONTEXT_S * SR))
        audio = self._audio()[start:]
        keep_from = self.done_until

        def run() -> str:
            pieces = self.decode(audio)
            return "".join(tok for tok, t in pieces if keep_from <= start + t * SR < keep_to)

        return self.executor.submit(run)

    def add(self, frame: np.ndarray):
        self.frames.append(frame)
        self.samples += len(frame)
        loudness = db(frame)
        self.loudest = max(self.loudest, loudness)
        if loudness > VOICE_DB:
            self.last_voice = self.samples
            self.quiet = 0
        else:
            self.quiet += len(frame)

        spoke = self.last_voice > self.done_until
        if self.cut_at is None:
            open_samples = self.samples - self.done_until
            if spoke and open_samples >= CUT_AFTER_S * SR and self.quiet >= CUT_PAUSE_S * SR:
                self.cut_at = self.samples - self.quiet // 2
            elif open_samples >= MAX_OPEN_S * SR:
                self.cut_at = self.samples  # no pause for a long time: cut anyway
        if self.cut_at is not None and self.samples >= self.cut_at + LOOKAHEAD_S * SR:
            self.pieces.append(self._transcribe(self.cut_at))
            self.done_until, self.cut_at, self.guess = self.cut_at, None, None
        elif (spoke and self.quiet >= SPECULATE_AFTER_S * SR
              # One background guess at a time; a newer one follows when it's done.
              and (self.guess is None or (self.guess[1].done() and self.guess[0] < self.last_voice))):
            self.guess = (self.samples, self._transcribe(float("inf")))

    def text(self) -> str:
        """The whole transcript. Blocks until the transcription is done."""
        if self.guess and self.last_voice <= self.guess[0]:
            # Nothing was said after the last background transcription: use it.
            last = self.guess[1]
        else:
            if self.guess:
                self.guess[1].cancel()  # outdated; skipped if it hasn't started yet
            last = self._transcribe(float("inf"))
        return ("".join(f.result() for f in self.pieces) + last.result()).strip()


class Dictation:
    """One reusable dictation runner. Callbacks run on a background thread."""

    def __init__(
        self,
        rec,
        on_levels: Callable[[list[float]], None] = lambda levels: None,
        on_done: Callable[[str, int, int], None] = lambda text, audio_ms, latency_ms: None,
        on_error: Callable[[str], None] = lambda message: None,
        on_silent: Callable[[], None] = lambda: None,
        device=None,
    ):
        self.rec = rec
        self.on_levels = on_levels
        self.on_done = on_done
        self.on_error = on_error
        self.on_silent = on_silent  # instead of on_done, when the mic recorded only silence
        self.device = device
        # One transcription at a time: they share the model and the CPU.
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="murmur-decode")
        self._recording = False
        self._cancelled = False
        self._busy = threading.Lock()

    @property
    def busy(self) -> bool:
        return self._busy.locked()

    def transcribe(self, audio: np.ndarray) -> str:
        """Transcribes on the decode thread, so it never runs at the same time as a dictation."""
        return self.executor.submit(engine.transcribe, self.rec, audio).result()

    def listen(self) -> bool:
        """Starts listening. Returns False if a dictation is still running."""
        if not self._busy.acquire(blocking=False):
            return False
        self._recording = True
        self._cancelled = False
        threading.Thread(target=self._run, name="murmur-dictation", daemon=True).start()
        return True

    def finish(self):
        """Stops listening and delivers the transcript."""
        self._recording = False

    def cancel(self):
        """Stops listening and throws the transcript away."""
        self._cancelled = True
        self._recording = False

    def _run(self):
        try:
            self._session()
        except Exception as e:
            log.exception("Dictation failed")
            self.on_error(f"Dictation failed: {e}")
        finally:
            self._recording = False
            self._busy.release()

    def _session(self):
        session = Session(lambda audio: engine.tokens(self.rec, audio), self.executor)
        chunks: queue.Queue[np.ndarray] = queue.Queue()
        levels: deque[float] = deque(maxlen=36)

        def callback(indata, frames, time_info, status):
            chunk = indata[:, 0].copy()
            chunks.put(chunk)
            levels.append(level(chunk))
            self.on_levels(list(levels))

        try:
            stream = sd.InputStream(
                samplerate=SR, channels=1, dtype="float32",
                blocksize=BLOCK, device=self.device, callback=callback,
            )
            stream.start()
        except Exception as e:
            log.exception("Couldn't open the microphone")
            self.on_error(f"The microphone is busy or unavailable: {e}")
            return

        stop_at = None
        while True:
            try:
                session.add(chunks.get(timeout=0.05))
            except queue.Empty:
                pass
            if not self._recording and stop_at is None:
                stop_at = time.monotonic() + TAIL_S
            if self._cancelled or (stop_at is not None and time.monotonic() >= stop_at):
                break
        stream.stop()
        stream.close()
        if self._cancelled:
            return
        while not chunks.empty():
            session.add(chunks.get_nowait())
        if session.silent:
            log.warning("The microphone recorded only silence (loudest frame %.0f dB)", session.loudest)
            self.on_silent()
            return

        t0 = time.perf_counter()
        text = cleanup.tidy(session.text())
        latency_ms = int((time.perf_counter() - t0) * 1000)
        self.on_done(text, session.samples * 1000 // SR, latency_ms)

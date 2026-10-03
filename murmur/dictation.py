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
import gc
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

from . import cleanup, engine, vocabulary

log = logging.getLogger(__name__)
SR = engine.SAMPLE_RATE
# Audio kept after the stop, for a word still being finished.
TAIL_S = 0.2
BLOCK = SR // 20  # 50 ms
# Frames louder than this count as speech. Room noise on a laptop mic is around -52 dB.
VOICE_DB = -45.0
# In a noisier room (a fan, air conditioning, the laptop's own fan under load) the room itself
# passes VOICE_DB, and with no pauses heard nothing is transcribed until the stop: 26 s of
# speech with noise at -43 dB took 2.5 s after it, against nothing with -47 dB. So speech must
# also be this much louder than the room, which is the quietest frame of the last NOISE_WINDOW_S
# (the gaps between words). A headset that gates its noise sends digital silence there, which
# leaves VOICE_DB in charge.
NOISE_MARGIN_DB = 10.0
NOISE_WINDOW_S = 3.0
# Transcribe in the background after this much quiet following speech.
SPECULATE_AFTER_S = 0.3
# Once this much speech is unfinished, finish it at the next pause of CUT_PAUSE_S...
CUT_AFTER_S = 5.0
CUT_PAUSE_S = 0.35
# ...and as it grows, at ever shorter ones: CUT_PAUSE_MIN_S once it's CUT_SHORTEN_S longer. A
# fluent talker rarely pauses long, and whatever is unfinished at the stop is what you wait for.
# Short pauses are safe cuts: each piece still hears the audio around it.
CUT_PAUSE_MIN_S = 0.15
CUT_SHORTEN_S = 4.0
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
# Opening the mic takes 40-75 ms, and this laptop's mic then fades in over about 300 ms, which
# clips a first word said right away. So the stream stays open this long after a dictation and
# the next one starts at full level (and the stop no longer waits ~65 ms for it to close). Not
# for ever: Windows shows the mic as in use while it's open. Audio between dictations is dropped.
MIC_KEEP_OPEN_S = 10.0
# Hands-free dictation finishes by itself (delivering the text) after this long without speech,
# so a forgotten one doesn't keep the mic open for ever. Long enough to stop and think.
HANDS_FREE_IDLE_S = 60.0


PUNCTUATION = ",.;:!?"


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
        self.recent: deque[float] = deque(maxlen=round(NOISE_WINDOW_S * SR / BLOCK))  # frames' dB

    @property
    def noise_db(self) -> float:
        """The room's loudness: the quietest recent frame."""
        return min(self.recent, default=-math.inf)

    @property
    def voice_db(self) -> float:
        """Frames louder than this are speech."""
        return max(VOICE_DB, self.noise_db + NOISE_MARGIN_DB)

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
        self.recent.append(loudness)
        if loudness > self.voice_db:
            self.last_voice = self.samples
            self.quiet = 0
        else:
            self.quiet += len(frame)

        spoke = self.last_voice > self.done_until
        if self.cut_at is None:
            open_samples = self.samples - self.done_until
            if spoke and open_samples >= CUT_AFTER_S * SR and self.quiet >= cut_pause(open_samples / SR) * SR:
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
        return join([f.result() for f in self.pieces] + [last.result()]).strip()


def cut_pause(open_s: float) -> float:
    """The pause that finishes a piece, once `open_s` seconds are unfinished (CUT_AFTER_S or more)."""
    t = min(1.0, max(0.0, (open_s - CUT_AFTER_S) / CUT_SHORTEN_S))
    return CUT_PAUSE_S - (CUT_PAUSE_S - CUT_PAUSE_MIN_S) * t


def join(pieces: list[str]) -> str:
    """Pieces' text in order. A comma or full stop right at a cut can be heard on both sides of
    it ("observed Phebe,, turning"), so a piece doesn't repeat the one its predecessor ended on."""
    out = ""
    for piece in pieces:
        head = piece.lstrip()
        if out and head[:1] in PUNCTUATION and out.rstrip()[-1:] == head[:1]:
            piece = head[1:]
        out += piece
    return out


class Dictation:
    """One reusable dictation runner. Callbacks run on a background thread."""

    def __init__(
        self,
        rec,
        on_levels: Callable[[list[float]], None] = lambda levels: None,
        on_done: Callable[[str, int, int], None] = lambda text, audio_ms, latency_ms: None,
        on_error: Callable[[str], None] = lambda message: None,
        on_silent: Callable[[], None] = lambda: None,
        on_auto_stop: Callable[[], None] = lambda: None,
        device=None,
        tidy: Callable[[str], str] = cleanup.tidy,
        vocab: vocabulary.Vocabulary | None = None,
    ):
        self.rec = rec
        self.tidy = tidy
        self.vocab = vocab  # terms to listen for (vocabulary.py); replaced when settings change
        self.on_levels = on_levels
        self.on_done = on_done
        self.on_error = on_error
        self.on_silent = on_silent  # instead of on_done, when the mic recorded only silence
        self.on_auto_stop = on_auto_stop  # hands-free finished by itself; on_done follows
        self.device = device
        self.hands_free = False  # set while listening, when it switches to hands-free
        # One transcription at a time: they share the model and the CPU.
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="murmur-decode")
        self._recording = False
        self._cancelled = False
        self._busy = threading.Lock()
        # The mic stream, kept open for a moment between dictations (see MIC_KEEP_OPEN_S).
        self._stream: sd.InputStream | None = None
        self._chunks: queue.Queue | None = None  # where audio goes while dictating
        self._levels: deque[float] = deque(maxlen=36)
        self._close_timer: threading.Timer | None = None
        self._mic_lock = threading.Lock()

    @property
    def busy(self) -> bool:
        return self._busy.locked()

    def transcribe(self, audio: np.ndarray) -> str:
        """Transcribes on the decode thread, so it never runs at the same time as a dictation."""
        return self.executor.submit(lambda: engine.transcribe(self._model(), audio, self.vocab)).result()

    @property
    def loaded(self) -> bool:
        return self.rec is not None

    def _model(self):
        """The model, loaded again first if it was unloaded to save memory. On the decode thread."""
        if self.rec is None:
            t0 = time.perf_counter()
            rec = engine.load()
            engine.transcribe(rec, np.zeros(SR, np.float32))  # warm-up, as at start
            self.rec = rec
            log.info("Speech model loaded again in %.1f s", time.perf_counter() - t0)
        return self.rec

    def unload(self):
        """Frees the model's memory; the next dictation loads it again while you speak. Queued
        on the decode thread, after any transcription still running."""
        def drop():
            if self.rec is None or self.busy:
                return
            self.rec = None
            engine.unload()
            gc.collect()
            log.info("Speech model unloaded to save memory")
        self.executor.submit(drop)

    def preload(self):
        """Starts loading the model now if it was unloaded, so it's there when needed."""
        if self.rec is None:
            self.executor.submit(self._model)

    def listen(self, hands_free=False) -> bool:
        """Starts listening. Returns False if a dictation is still running."""
        if not self._busy.acquire(blocking=False):
            return False
        self._recording = True
        self._cancelled = False
        self.hands_free = hands_free
        # If the model was unloaded, it loads while you speak; the text waits for it, not the mic.
        self.preload()
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

    def _callback(self, indata, frames, time_info, status):
        chunks = self._chunks
        if chunks is None:
            return  # between dictations, while the stream is kept open: dropped unheard
        chunk = indata[:, 0].copy()
        chunks.put(chunk)
        self._levels.append(level(chunk))
        self.on_levels(list(self._levels))

    def _open_mic(self) -> queue.Queue:
        """Starts taking audio, from the stream still open after the last dictation if there is one."""
        with self._mic_lock:
            if self._close_timer:
                self._close_timer.cancel()
                self._close_timer = None
            self._levels = deque(maxlen=36)
            self._chunks = queue.Queue()
            if self._stream is not None and not self._stream.active:
                self._close_stream()  # stopped by itself, e.g. the device was unplugged
            if self._stream is None:
                try:
                    self._stream = sd.InputStream(
                        samplerate=SR, channels=1, dtype="float32",
                        blocksize=BLOCK, device=self.device, callback=self._callback,
                    )
                    self._stream.start()
                except Exception:
                    self._chunks = None
                    self._close_stream()
                    raise
            return self._chunks

    def _release_mic(self):
        """Stops taking audio, and closes the stream once nobody dictates for MIC_KEEP_OPEN_S."""
        with self._mic_lock:
            self._chunks = None
            self._close_timer = threading.Timer(MIC_KEEP_OPEN_S, self._close_idle)
            self._close_timer.daemon = True
            self._close_timer.start()

    def _close_idle(self):
        with self._mic_lock:
            if self._chunks is None:
                self._close_stream()

    def close(self):
        """Closes the mic now, rather than after the grace period (on quit)."""
        with self._mic_lock:
            if self._close_timer:
                self._close_timer.cancel()
            self._chunks = None
            self._close_stream()

    def _close_stream(self):
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                log.warning("Couldn't close the microphone", exc_info=True)

    def _session(self):
        session = Session(lambda audio: engine.tokens(self._model(), audio, self.vocab), self.executor)
        try:
            chunks = self._open_mic()
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
            if self._recording and self.hands_free and session.quiet >= HANDS_FREE_IDLE_S * SR:
                log.info("Hands-free dictation finished after %.0f s without speech", HANDS_FREE_IDLE_S)
                self._recording = False
                self.on_auto_stop()
            if not self._recording and stop_at is None:
                stop_at = time.monotonic() + TAIL_S
            if self._cancelled or (stop_at is not None and time.monotonic() >= stop_at):
                break
        self._release_mic()
        if self._cancelled:
            return
        while not chunks.empty():
            session.add(chunks.get_nowait())
        if session.silent:
            log.warning("The microphone recorded only silence (loudest frame %.0f dB)", session.loudest)
            self.on_silent()
            return

        t0 = time.perf_counter()
        text = self.tidy(session.text())
        latency_ms = int((time.perf_counter() - t0) * 1000)
        log.info("Transcribed in %d %s; room noise %.0f dB, speech above %.0f dB", len(session.pieces) + 1,
                 "piece" if not session.pieces else "pieces", session.noise_db, session.voice_db)
        self.on_done(text, session.samples * 1000 // SR, latency_ms)

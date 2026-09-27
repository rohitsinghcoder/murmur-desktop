"""Records from the microphone and transcribes while you speak.

Port of the Android app's DictationService.runSession: the mic is read on its own (audio
callback) thread and queued, so a slow decode step never makes the recorder drop audio, and
everything said before the stop still gets transcribed.
"""
import math
import queue
import threading
import time
from collections import deque
from typing import Callable

import numpy as np
import sounddevice as sd

from . import cleanup, engine

# Audio kept after the stop, for a word still being finished.
TAIL_S = 0.2
BLOCK = engine.SAMPLE_RATE // 20  # 50 ms


def level(chunk: np.ndarray) -> float:
    """Loudness of a chunk mapped to 0..1: room noise stays near 0, normal speech fills it."""
    rms = math.sqrt(float(np.mean(chunk * chunk))) if len(chunk) else 0.0
    db = 20 * math.log10(rms + 1e-6)
    x = min(1.0, max(0.0, (db + 50) / 40))
    return x * x


class Dictation:
    """One reusable dictation session runner. Callbacks run on a background thread."""

    def __init__(
        self,
        rec,
        on_partial: Callable[[str], None] = lambda text: None,
        on_levels: Callable[[list[float]], None] = lambda levels: None,
        on_done: Callable[[str, int, int], None] = lambda text, audio_ms, latency_ms: None,
        on_error: Callable[[str], None] = lambda message: None,
        device=None,
    ):
        self.rec = rec
        self.on_partial = on_partial
        self.on_levels = on_levels
        self.on_done = on_done
        self.on_error = on_error
        self.device = device
        self._recording = False
        self._cancelled = False
        self._busy = threading.Lock()

    @property
    def busy(self) -> bool:
        return self._busy.locked()

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
            self.on_error(f"Dictation failed: {e}")
        finally:
            self._recording = False
            self._busy.release()

    def _session(self):
        transcriber = engine.Transcriber(self.rec)
        chunks: queue.Queue[np.ndarray] = queue.Queue()
        levels: deque[float] = deque(maxlen=36)

        def callback(indata, frames, time_info, status):
            chunk = indata[:, 0].copy()
            chunks.put(chunk)
            levels.append(level(chunk))
            self.on_levels(list(levels))

        try:
            stream = sd.InputStream(
                samplerate=engine.SAMPLE_RATE, channels=1, dtype="float32",
                blocksize=BLOCK, device=self.device, callback=callback,
            )
            stream.start()
        except Exception as e:
            self.on_error(f"The microphone is busy or unavailable: {e}")
            return

        samples = 0
        stop_at = None
        ended = False
        while not ended:
            pending = []
            try:
                pending.append(chunks.get(timeout=0.05))
            except queue.Empty:
                pass
            if not self._recording and stop_at is None:
                stop_at = time.monotonic() + TAIL_S
            if self._cancelled or (stop_at is not None and time.monotonic() >= stop_at):
                stream.stop()
                stream.close()
                ended = True
            # Catch up in one step if audio queued up while the last chunk was decoding.
            while True:
                try:
                    pending.append(chunks.get_nowait())
                except queue.Empty:
                    break
            if not self._cancelled and pending:
                chunk = np.concatenate(pending)
                samples += len(chunk)
                self.on_partial(cleanup.tidy(transcriber.accept(chunk)))

        if self._cancelled:
            return
        t0 = time.perf_counter()
        text = cleanup.tidy(transcriber.finish())
        latency_ms = int((time.perf_counter() - t0) * 1000)
        self.on_done(text, samples * 1000 // engine.SAMPLE_RATE, latency_ms)

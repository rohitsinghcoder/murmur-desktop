"""Owns the streaming speech model (NVIDIA Nemotron Speech Streaming via sherpa-onnx).

Port of the Android app's Engine.kt. The model is large (~650 MB), so it is loaded once and
kept in memory.
"""
import threading
from pathlib import Path

import numpy as np
import sherpa_onnx

SAMPLE_RATE = 16000
MODEL_NAME = "sherpa-onnx-nemotron-speech-streaming-en-0.6b-560ms-int8-2026-04-25"
MODEL_DIR = Path(__file__).resolve().parent.parent / "models" / MODEL_NAME

_lock = threading.Lock()
_recognizer: sherpa_onnx.OnlineRecognizer | None = None


def _find(directory: Path, prefix: str) -> Path | None:
    files = [f for f in directory.glob(f"{prefix}*.onnx")]
    return min(files, key=lambda f: 0 if "int8" in f.name else 1, default=None)


def is_model_installed(directory: Path = MODEL_DIR) -> bool:
    return all(_find(directory, p) for p in ("encoder", "decoder", "joiner")) and (
        directory / "tokens.txt"
    ).exists()


def is_loaded() -> bool:
    return _recognizer is not None


def load(num_threads: int = 4, directory: Path = MODEL_DIR) -> sherpa_onnx.OnlineRecognizer:
    global _recognizer
    with _lock:
        if _recognizer is not None:
            return _recognizer
        if not is_model_installed(directory):
            raise FileNotFoundError(f"Speech model not found in {directory}. Run scripts/fetch_model.py.")
        _recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
            tokens=str(directory / "tokens.txt"),
            encoder=str(_find(directory, "encoder")),
            decoder=str(_find(directory, "decoder")),
            joiner=str(_find(directory, "joiner")),
            num_threads=num_threads,
            sample_rate=SAMPLE_RATE,
            feature_dim=128,
            dither=0.0,
            # Split long dictation into segments at natural pauses, which keeps each decode
            # short. The user still decides when dictation ends.
            enable_endpoint_detection=True,
            rule1_min_trailing_silence=2.4,
            rule2_min_trailing_silence=1.2,
            rule3_min_utterance_length=30.0,
            decoding_method="greedy_search",
            provider="cpu",
        )
        return _recognizer


class Transcriber:
    """One dictation: feed audio in, read the running transcript out."""

    def __init__(self, rec: sherpa_onnx.OnlineRecognizer):
        self.rec = rec
        self.stream = rec.create_stream()
        self.committed = ""

    def _join(self, tail: str) -> str:
        return " ".join(s for s in (self.committed, tail) if s.strip())

    def accept(self, samples: np.ndarray) -> str:
        """Adds audio and returns the transcript so far."""
        self.stream.accept_waveform(SAMPLE_RATE, samples)
        while self.rec.is_ready(self.stream):
            self.rec.decode_stream(self.stream)
        partial = self.rec.get_result(self.stream).strip()
        if self.rec.is_endpoint(self.stream):
            if partial:
                self.committed = self._join(partial)
            self.rec.reset(self.stream)
            return self.committed
        return self._join(partial)

    def finish(self) -> str:
        """Flushes the last chunk and returns the final transcript."""
        # Silence padding lets the streaming encoder emit the final words.
        self.stream.accept_waveform(SAMPLE_RATE, np.zeros(SAMPLE_RATE * 8 // 10, dtype=np.float32))
        self.stream.input_finished()
        while self.rec.is_ready(self.stream):
            self.rec.decode_stream(self.stream)
        return self._join(self.rec.get_result(self.stream).strip())

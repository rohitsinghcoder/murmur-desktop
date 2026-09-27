"""Owns the speech model: NVIDIA Parakeet TDT 0.6B v2 (English) via sherpa-onnx.

Unlike the Android app's streaming model, Parakeet hears a whole utterance at once, which gives
clearly better punctuation and no stray capitals where a streaming model split at a pause. The
model is large (~630 MB), so it is loaded once and kept in memory.
"""
import threading
from pathlib import Path

import numpy as np
import sherpa_onnx

SAMPLE_RATE = 16000
MODEL_NAME = "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
MODEL_DIR = Path(__file__).resolve().parent.parent / "models" / MODEL_NAME
MODEL_LABEL = "NVIDIA Parakeet TDT 0.6B v2 (int8)"

_lock = threading.Lock()
_recognizer: sherpa_onnx.OfflineRecognizer | None = None


def _find(directory: Path, prefix: str) -> Path | None:
    files = [f for f in directory.glob(f"{prefix}*.onnx")]
    return min(files, key=lambda f: 0 if "int8" in f.name else 1, default=None)


def is_model_installed(directory: Path = MODEL_DIR) -> bool:
    return all(_find(directory, p) for p in ("encoder", "decoder", "joiner")) and (
        directory / "tokens.txt"
    ).exists()


def load(num_threads: int = 4, directory: Path = MODEL_DIR) -> sherpa_onnx.OfflineRecognizer:
    global _recognizer
    with _lock:
        if _recognizer is not None:
            return _recognizer
        if not is_model_installed(directory):
            raise FileNotFoundError(f"Speech model not found in {directory}. Run scripts/fetch_model.py.")
        _recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
            encoder=str(_find(directory, "encoder")),
            decoder=str(_find(directory, "decoder")),
            joiner=str(_find(directory, "joiner")),
            tokens=str(directory / "tokens.txt"),
            num_threads=num_threads,
            sample_rate=SAMPLE_RATE,
            feature_dim=128,
            model_type="nemo_transducer",
            decoding_method="greedy_search",
            provider="cpu",
        )
        return _recognizer


def tokens(rec: sherpa_onnx.OfflineRecognizer, audio: np.ndarray) -> list[tuple[str, float]]:
    """The recognised pieces of text for 16 kHz mono audio, each with the time (seconds into the
    audio) it was heard. A piece starting a new word begins with a space, so joining them all
    gives the text. Call from one thread at a time."""
    if len(audio) < SAMPLE_RATE // 10:
        return []
    stream = rec.create_stream()
    stream.accept_waveform(SAMPLE_RATE, audio)
    rec.decode_stream(stream)
    return list(zip(stream.result.tokens, stream.result.timestamps))


def transcribe(rec: sherpa_onnx.OfflineRecognizer, audio: np.ndarray) -> str:
    """Text for a stretch of 16 kHz mono audio. Call from one thread at a time."""
    return "".join(t for t, _ in tokens(rec, audio)).strip()

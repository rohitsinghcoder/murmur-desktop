"""Owns the speech model: NVIDIA Parakeet TDT 0.6B v2 (English) via sherpa-onnx.

Unlike the Android app's streaming model, Parakeet hears a whole utterance at once, which gives
clearly better punctuation and no stray capitals where a streaming model split at a pause. The
model is large (~630 MB), so it is loaded once and kept in memory.

It decodes with beam search rather than greedily, which hotwords need (vocabulary.py); a second
recognizer for greedy decoding would load the model twice. Beam search is about 14% slower and
was as accurate as greedy on the clips tested.
"""
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import sherpa_onnx

from . import vocabulary

SAMPLE_RATE = 16000
MODEL_NAME = "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
# The installed (frozen) app keeps the model with the user's data in ~/.murmur, where the installer
# puts it, so upgrading Murmur doesn't download it again.
FROZEN = getattr(sys, "frozen", False)
MODEL_DIR = (Path.home() / ".murmur" if FROZEN else Path(__file__).resolve().parent.parent) / "models" / MODEL_NAME
MODEL_LABEL = "NVIDIA Parakeet TDT 0.6B v2 (int8)"

_lock = threading.Lock()
_recognizer: sherpa_onnx.OfflineRecognizer | None = None
# The decode with hotwords runs alongside the plain one: 0.14 s per second of audio for both,
# where one after the other took 0.19 (one alone: 0.10). Same results either way.
_steer = ThreadPoolExecutor(max_workers=1, thread_name_prefix="murmur-steer")


def _find(directory: Path, prefix: str) -> Path | None:
    files = [f for f in directory.glob(f"{prefix}*.onnx")]
    return min(files, key=lambda f: 0 if "int8" in f.name else 1, default=None)


def is_model_installed(directory: Path = MODEL_DIR) -> bool:
    return all(_find(directory, p) for p in ("encoder", "decoder", "joiner")) and (
        directory / "tokens.txt"
    ).exists()


def _bpe_vocab(directory: Path) -> Path:
    """The model's word pieces with their scores, which sherpa-onnx needs to split hotwords into
    them. Made from tokens.txt: in a BPE model a piece's id is its merge order."""
    path = directory / "bpe.vocab"
    if not path.exists():
        lines = (directory / "tokens.txt").read_text(encoding="utf-8").splitlines()
        pieces = [line.rsplit(" ", 1)[0] for line in lines if line.strip()]
        tmp = path.with_suffix(".tmp")
        tmp.write_text("".join(f"{piece}\t{-i}\n" for i, piece in enumerate(pieces)), encoding="utf-8", newline="\n")
        tmp.replace(path)
    return path


def load(num_threads: int = 4, directory: Path = MODEL_DIR) -> sherpa_onnx.OfflineRecognizer:
    global _recognizer
    with _lock:
        if _recognizer is not None:
            return _recognizer
        if not is_model_installed(directory):
            fix = "Run the Murmur installer again to download it" if FROZEN else "Run scripts/fetch_model.py"
            raise FileNotFoundError(f"Speech model not found in {directory}. {fix}.")
        _recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
            encoder=str(_find(directory, "encoder")),
            decoder=str(_find(directory, "decoder")),
            joiner=str(_find(directory, "joiner")),
            tokens=str(directory / "tokens.txt"),
            num_threads=num_threads,
            sample_rate=SAMPLE_RATE,
            feature_dim=128,
            model_type="nemo_transducer",
            decoding_method="modified_beam_search",
            max_active_paths=4,
            modeling_unit="bpe",
            bpe_vocab=str(_bpe_vocab(directory)),
            hotwords_score=vocabulary.SCORE,
            provider="cpu",
        )
        return _recognizer


def unload():
    """Drops the model, freeing its memory (about 670 MB). load() brings it back (~3.5 s)."""
    global _recognizer
    with _lock:
        _recognizer = None


def _decode(rec: sherpa_onnx.OfflineRecognizer, audio: np.ndarray, hotwords: str = "") -> list[tuple[str, float]]:
    stream = rec.create_stream(hotwords) if hotwords else rec.create_stream()
    stream.accept_waveform(SAMPLE_RATE, audio)
    rec.decode_stream(stream)
    return list(zip(stream.result.tokens, stream.result.timestamps))


def tokens(rec: sherpa_onnx.OfflineRecognizer, audio: np.ndarray,
           vocab: vocabulary.Vocabulary | None = None) -> list[tuple[str, float]]:
    """The recognised pieces of text for 16 kHz mono audio, each with the time (seconds into the
    audio) it was heard. A piece starting a new word begins with a space, so joining them all
    gives the text. With a vocabulary, its terms are listened for too (see vocabulary.py), which
    takes a second decode, run at the same time. Call from one thread at a time."""
    if len(audio) < SAMPLE_RATE // 10:
        return []
    if not vocab:
        return _decode(rec, audio)
    steered = _steer.submit(_decode, rec, audio, vocab.hotwords)
    plain = _decode(rec, audio)
    return vocab.merge(plain, steered.result())


def transcribe(rec: sherpa_onnx.OfflineRecognizer, audio: np.ndarray,
               vocab: vocabulary.Vocabulary | None = None) -> str:
    """Text for a stretch of 16 kHz mono audio. Call from one thread at a time."""
    return "".join(t for t, _ in tokens(rec, audio, vocab)).strip()

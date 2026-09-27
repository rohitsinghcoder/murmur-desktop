"""Speed test: how fast the speech model runs on this machine.

    python bench.py                 # the model's sample wavs, 4 and 6 threads
    python bench.py my.wav -t 6     # your own recording

Reports how long each clip takes to transcribe and the real-time factor (transcription time /
audio length; 0.1 means 10 s of speech takes 1 s).
"""
import argparse
import time
from pathlib import Path

import numpy as np
import soundfile as sf

from murmur import engine


def read(path: Path) -> np.ndarray:
    audio, sr = sf.read(path, dtype="float32", always_2d=True)
    audio = audio.mean(axis=1)
    if sr != engine.SAMPLE_RATE:
        n = int(len(audio) * engine.SAMPLE_RATE / sr)
        audio = np.interp(np.linspace(0, len(audio), n, endpoint=False), np.arange(len(audio)), audio)
    return audio.astype(np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("wavs", nargs="*", type=Path)
    ap.add_argument("-t", "--threads", type=int, nargs="*", default=[4, 6])
    args = ap.parse_args()
    wavs = args.wavs or sorted((engine.MODEL_DIR / "test_wavs").glob("*.wav"))

    for threads in args.threads:
        engine._recognizer = None
        t0 = time.perf_counter()
        rec = engine.load(num_threads=threads)
        engine.transcribe(rec, np.zeros(engine.SAMPLE_RATE, dtype=np.float32))  # warm-up
        print(f"\n=== {threads} threads (load + warm-up {time.perf_counter() - t0:.1f}s) ===")
        total_audio = total_time = 0.0
        for wav in wavs:
            audio = read(wav)
            t = time.perf_counter()
            text = engine.transcribe(rec, audio)
            took = time.perf_counter() - t
            secs = len(audio) / engine.SAMPLE_RATE
            total_audio += secs
            total_time += took
            print(f"{wav.name}: {secs:.1f}s audio in {took * 1000:.0f} ms (RTF {took / secs:.3f})")
            print(f"  {text}")
        print(f"Overall RTF: {total_time / total_audio:.3f}")


if __name__ == "__main__":
    main()

"""Speed test: how fast the speech model runs on this machine.

    python bench.py                 # the model's sample wavs, 4 and 6 threads
    python bench.py my.wav -t 6     # your own recording (16 kHz mono works best)

Audio is fed in 100 ms chunks, like the mic does. Reports real-time factor (decode time / audio
length; below 1 keeps up with speech) and finish latency (the wait after you stop talking).
"""
import argparse
import time
from pathlib import Path

import numpy as np
import soundfile as sf

from murmur import engine

CHUNK = engine.SAMPLE_RATE // 10


def read(path: Path) -> np.ndarray:
    audio, sr = sf.read(path, dtype="float32", always_2d=True)
    audio = audio.mean(axis=1)
    if sr != engine.SAMPLE_RATE:
        n = int(len(audio) * engine.SAMPLE_RATE / sr)
        audio = np.interp(np.linspace(0, len(audio), n, endpoint=False), np.arange(len(audio)), audio)
    return audio.astype(np.float32)


def run(rec, audio: np.ndarray):
    t = engine.Transcriber(rec)
    t0 = time.perf_counter()
    for i in range(0, len(audio), CHUNK):
        t.accept(audio[i : i + CHUNK])
    t1 = time.perf_counter()
    text = t.finish()
    t2 = time.perf_counter()
    return text, t1 - t0, t2 - t1


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
        run(rec, np.zeros(engine.SAMPLE_RATE, dtype=np.float32))  # warm-up
        print(f"\n=== {threads} threads (load + warm-up {time.perf_counter() - t0:.1f}s) ===")
        total_audio = total_decode = 0.0
        for wav in wavs:
            audio = read(wav)
            text, decode, finish = run(rec, audio)
            secs = len(audio) / engine.SAMPLE_RATE
            total_audio += secs
            total_decode += decode + finish
            print(f"{wav.name}: {secs:.1f}s audio, RTF {(decode + finish) / secs:.2f}, finish {finish * 1000:.0f} ms")
            print(f"  {text}")
        print(f"Overall RTF: {total_decode / total_audio:.2f}")


if __name__ == "__main__":
    main()

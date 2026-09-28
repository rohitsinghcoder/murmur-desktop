"""Does dictation.Session's piece stitching work with a candidate model? (see docs/LANGUAGES.md)

    python scripts/bench_stitch.py parakeet-v3 nemotron-3.5

Joins test clips with 0.6 s pauses into one long "dictation" per language, feeds it to
dictation.Session 50 ms at a time like the microphone would (pieces are cut at pauses once 5 s is
open and transcribed with context), and compares the stitched text with the whole recording
transcribed in one go. Words lost or doubled at the cuts show up as differences. Also compares
each model's word start times with Parakeet v2's (whose timestamps Session was built on).
"""
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bench_models as b  # noqa: E402
from murmur import dictation  # noqa: E402

GAP = np.zeros(int(0.6 * b.SR), np.float32)


def long_audio(group: str) -> np.ndarray:
    clips = [c for c in b.clip_set()[group] if c.parent == b.CLIPS]
    parts = []
    for c in clips:
        parts += [b.read(c), GAP]
    return np.concatenate(parts)


def words_with_times(toks, ts):
    """Word start times: a token starting with a space (or the first) starts a word."""
    out = []
    for i, (t, s) in enumerate(zip(toks, ts)):
        if i == 0 or t.startswith(" ") or t.startswith("▁"):
            out.append((t.strip(" ▁"), s))
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    names = sys.argv[1:] or ["parakeet-v2", "parakeet-v3", "nemotron-3.5"]
    base_ref = {}
    for name in names:
        rec = b.build(name, "auto")
        rec.decode(np.zeros(b.SR, np.float32), "auto")
        for group, lang in [("en", "en"), ("en-tts", "en"), ("hi", "hi"), ("hinglish", "hi")]:
            audio = long_audio(group)
            text, toks, ts, _ = rec.decode(audio, lang)
            whole = text.strip()

            def decode(a, lang=lang):
                _, tk, tt, _ = rec.decode(a, lang)
                return list(zip(tk, tt))

            with ThreadPoolExecutor(max_workers=1) as ex:
                s = dictation.Session(decode, ex)
                for i in range(0, len(audio), dictation.BLOCK):
                    s.add(audio[i:i + dictation.BLOCK])
                stitched = s.text()
                n_pieces = len(s.pieces) + 1
            a, c = b.normalise(whole), b.normalise(stitched)
            diff = b.edits(a, c)
            print(f"\n[{name}] {group}: {len(audio) / b.SR:.0f}s, {n_pieces} pieces, "
                  f"{diff} word edits between stitched and whole ({len(a)} words)")
            print(f"  whole:    {whole[:300]}")
            print(f"  stitched: {stitched[:300]}")
            if group in ("en", "en-tts"):
                w = words_with_times(toks, ts)
                if name == "parakeet-v2":
                    base_ref[group] = w
                elif group in base_ref:
                    ref = base_ref[group]
                    # Pair words by position when the word lists match closely.
                    pairs = [(x[1], y[1]) for x, y in zip(ref, w) if x[0].lower().strip(",.?") == y[0].lower().strip(",.?")]
                    if pairs:
                        d = np.array([y - x for x, y in pairs])
                        print(f"  word start vs Parakeet v2: {len(pairs)} matched words, mean {d.mean():+.2f}s, "
                              f"max |{np.abs(d).max():.2f}|s")


if __name__ == "__main__":
    main()

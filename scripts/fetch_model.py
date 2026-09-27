"""Downloads the Parakeet speech model (~460 MB download, ~630 MB unpacked) into models/. Safe to re-run."""
import sys
import tarfile
import urllib.request
from pathlib import Path

MODEL = "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
URL = f"https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/{MODEL}.tar.bz2"
MODELS = Path(__file__).resolve().parent.parent / "models"


def progress(blocks, block_size, total):
    done = blocks * block_size
    if total > 0:
        pct = min(100, done * 100 // total)
        sys.stdout.write(f"\r  {done >> 20} / {total >> 20} MB ({pct}%)")
        sys.stdout.flush()


def main():
    if (MODELS / MODEL / "tokens.txt").exists():
        print("Model already downloaded.")
        return
    MODELS.mkdir(exist_ok=True)
    archive = MODELS / f"{MODEL}.tar.bz2"
    part = archive.with_suffix(".bz2.part")
    print("Downloading the speech model (~460 MB)...")
    urllib.request.urlretrieve(URL, part, progress)
    part.replace(archive)
    print("\nUnpacking...")
    with tarfile.open(archive, "r:bz2") as tar:
        tar.extractall(MODELS, filter="data")
    archive.unlink()
    print(f"Done: {MODELS / MODEL}")


if __name__ == "__main__":
    main()

"""Try dictation in the terminal: Enter to start, Enter to stop.

    python -m murmur.console
"""
import threading
import time

from . import dictation, engine


def main():
    print("Loading the speech model...")
    t0 = time.perf_counter()
    rec = engine.load()
    print(f"Loaded in {time.perf_counter() - t0:.1f}s.")
    done = threading.Event()

    def finished(text, audio_ms, latency_ms):
        print(f"\n{text}\n({audio_ms / 1000:.1f}s audio, ready {latency_ms} ms after you stopped)\n")
        done.set()

    def error(message):
        print(f"\n{message}")
        done.set()

    d = dictation.Dictation(rec, on_done=finished, on_error=error)
    while True:
        if input("Press Enter to speak (q to quit): ").strip().lower() == "q":
            return
        done.clear()
        d.listen()
        input("Listening... press Enter to stop.")
        d.finish()
        done.wait()


if __name__ == "__main__":
    main()

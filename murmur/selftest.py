"""Checks that a Murmur build works, without its keyboard hook and without showing anything.

    python -m murmur.selftest [OUT_DIR]
    Murmur.exe --selftest [OUT_DIR]        (the frozen build; see installer/launcher.py)

Starts the real App, but with the keyboard hook and the tray icon swapped for stand-ins and the
bar and window rendered off-screen, so it's safe while another Murmur is running (it never
touches the single-instance lock either). History, settings and the log point at a temporary
folder with sample entries. It then checks that the model loads, that the model's sample
recording (test_wavs/0.wav) is transcribed right, that UI Automation loads for spacing, and that
the window's page loads with the Qt bridge connected.

Writes OUT_DIR/selftest.json, window.png and pill.png (OUT_DIR defaults to
%TEMP%\\murmur-selftest). Exit code 0 if every check passed.
"""
import json
import re
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path

# What the model's test_wavs/0.wav says (punctuation and case aside).
EXPECTED = ("Well, I don't wish to see it any more, observed Phebe, turning away her eyes. "
            "It is certainly very like the old portrait.")
SAMPLES = [
    "Can we move the design review to Thursday at 3:30 PM?",
    "The invoice came to ₹2,450, so I paid it this morning.",
    "Thanks for the notes. I'll send the draft over by Friday.",
]
TIMEOUT_S = 180


def _words(text: str) -> list[str]:
    return re.sub(r"[^a-z0-9' ]", " ", text.lower()).split()


def _wait(qt, done, timeout_s: float) -> bool:
    end = time.monotonic() + timeout_s
    while not done() and time.monotonic() < end:
        qt.processEvents()
        time.sleep(0.01)
    return done()


def _not_blank(image) -> bool:
    """True if the image has more than one colour (a failed render is a flat fill)."""
    w, h = image.width(), image.height()
    colours = {image.pixel(x * w // 17, y * h // 13) for x in range(1, 17) for y in range(1, 13)}
    return len(colours) > 3


def _process_age() -> float:
    """Seconds since this process was started."""
    import ctypes
    k = ctypes.windll.kernel32
    k.GetCurrentProcess.restype = ctypes.c_void_p
    k.GetProcessTimes.argtypes = [ctypes.c_void_p] + [ctypes.c_void_p] * 4
    created, _exit, _kernel, _user, now = (ctypes.c_ulonglong() for _ in range(5))  # FILETIMEs
    k.GetProcessTimes(k.GetCurrentProcess(), *(ctypes.byref(t) for t in (created, _exit, _kernel, _user)))
    k.GetSystemTimePreciseAsFileTime(ctypes.byref(now))
    return (now.value - created.value) / 1e7


def run(out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    report = {"frozen": bool(getattr(sys, "frozen", False)), "executable": sys.executable, "checks": {}}

    def check(name, ok, **detail):
        report["checks"][name] = {"ok": bool(ok), **detail}
        return ok

    # Sample data in place of the user's history, settings and log.
    from . import history, logfile, settings
    data = Path(tempfile.mkdtemp(prefix="murmur-selftest-"))
    history.DIR, history.FILE, history._OLD_FILE = data, data / "history.jsonl", data / "old.jsonl"
    settings.FILE = data / "settings.json"
    logfile.DIR, logfile.FILE = data, out / "murmur.log"
    now = int(time.time() * 1000)
    with history.FILE.open("w", encoding="utf-8") as f:
        for i, text in enumerate(SAMPLES):
            f.write(json.dumps({"time": now - (len(SAMPLES) - i) * 3_600_000, "text": text,
                                "audioMs": 3500, "app": "notepad.exe"}, ensure_ascii=False) + "\n")
    logfile.setup()

    # Imports Qt WebEngine before the QApplication, like __main__ does.
    from . import __main__ as murmur_main
    from . import engine, hotkey, spacing
    from .ui import style, window
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QApplication, QSystemTrayIcon

    qt = QApplication.instance() or QApplication([sys.argv[0]])
    qt.setQuitOnLastWindowClosed(False)
    style.load_fonts()
    qt.setFont(QFont("Geist", 10))

    check("resources", window.WEB.joinpath("index.html").is_file()
          and "Geist" in QFontDatabase.families(),
          web=str(window.WEB), fonts=str(style.FONTS))
    check("model_files", engine.is_model_installed(), model_dir=str(engine.MODEL_DIR))

    class NoHook:
        """Stands in for hotkey.HoldToTalk: no keyboard hook."""
        typed_at = 0.0

        def __init__(self, *args, **kwargs):
            pass

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    class HiddenTray(QSystemTrayIcon):
        def show(self):
            pass

        def showMessage(self, *args, **kwargs):
            pass

    class OffscreenPill(murmur_main.Pill):
        def __init__(self):
            super().__init__()
            self.setAttribute(Qt.WA_DontShowOnScreen)

    hotkey.HoldToTalk = NoHook
    murmur_main.QSystemTrayIcon = HiddenTray
    murmur_main.Pill = OffscreenPill

    app = murmur_main.App(qt)
    # The window, opened as main() does: right away, while the model loads in the background.
    win = window.MainWindow(app)
    win.setAttribute(Qt.WA_DontShowOnScreen)
    app.window = win
    page_loaded = []  # (ok, seconds since the process started)
    win.view.page().loadFinished.connect(lambda ok: page_loaded.append((ok, round(_process_age(), 2))))
    app.show_window()

    loaded, failed = [], []
    app.loaded.connect(loaded.append)
    app.load_failed.connect(failed.append)
    t0 = time.perf_counter()
    _wait(qt, lambda: loaded or failed, TIMEOUT_S)
    check("model_load", loaded, secs=round(time.perf_counter() - t0, 2),
          error=failed[0] if failed else None)

    if loaded:
        import soundfile as sf
        audio, _ = sf.read(engine.MODEL_DIR / "test_wavs" / "0.wav", dtype="float32")
        t0 = time.perf_counter()
        text = app.dictation.transcribe(audio)
        took = time.perf_counter() - t0
        check("transcribe", _words(text) == _words(EXPECTED), text=text,
              audio_secs=round(len(audio) / engine.SAMPLE_RATE, 2), secs=round(took, 3),
              rtf=round(took / (len(audio) / engine.SAMPLE_RATE), 3))

    # UI Automation (comtypes' generated wrappers), which spacing loads on its own thread.
    app.caret._executor.submit(lambda: None).result(timeout=60)
    uia = sys.modules.get("comtypes.gen.UIAutomationClient")
    check("ui_automation", app.caret._uia is not None,
          wrappers=getattr(uia, "__file__", None) if uia else None)
    check("spacing", spacing.needs_space("How", "o.") and not spacing.needs_space("How", "( "))

    # The start/stop sounds (Qt Multimedia and assets/*.wav), loaded but not played.
    from PySide6.QtMultimedia import QSoundEffect
    from . import sounds
    effects = sounds.Sounds()
    effects.set_enabled(True)
    _wait(qt, lambda: all(e.status() in (QSoundEffect.Ready, QSoundEffect.Error)
                          for e in effects._effects.values()), 15)
    check("sounds", all(e.status() == QSoundEffect.Ready for e in effects._effects.values()),
          assets=str(sounds.ASSETS))

    # The window, grabbed once the page has shown the bridge's state.
    _wait(qt, lambda: page_loaded, 60)
    _wait(qt, lambda: False, 1.0)  # the page renders the latest state
    probe = []
    win.view.page().runJavaScript(
        "JSON.stringify({bridge: !!(window.qt && window.QWebChannel),"
        " status: (document.querySelector('[data-status-text]') || {}).textContent,"
        " load: (document.querySelector('[data-load]') || {}).textContent,"
        " geist: document.fonts.check('13px Geist'),"
        " text: document.body.innerText.length})", 0, probe.append)
    _wait(qt, lambda: probe, 15)
    page = json.loads(probe[0]) if probe and probe[0] else {}
    shot = win.view.grab().toImage()
    shot.save(str(out / "window.png"))
    check("window", page_loaded and page_loaded[0][0] and page.get("bridge") and page.get("geist")
          and page.get("text", 0) > 100 and _not_blank(shot),
          secs_from_launch_to_page=page_loaded[0][1] if page_loaded else None,
          page=page, screenshot=str(out / "window.png"))

    app.pill.grab().save(str(out / "pill.png"))

    app.quit()
    shutil.rmtree(data, ignore_errors=True)
    report["ok"] = all(c["ok"] for c in report["checks"].values())
    return report


def main():
    args = [a for a in sys.argv[1:] if a != "--selftest"]
    out = Path(args[0]) if args else Path(tempfile.gettempdir()) / "murmur-selftest"
    try:
        report = run(out)
    except Exception:
        report = {"ok": False, "error": traceback.format_exc()}
    out.mkdir(parents=True, exist_ok=True)
    (out / "selftest.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    if sys.stdout:  # the frozen app has no console
        print(json.dumps(report, indent=2))
    sys.exit(0 if report.get("ok") else 1)


if __name__ == "__main__":
    main()

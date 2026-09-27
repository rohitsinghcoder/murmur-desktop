# Murmur Desktop

Private, on-device voice typing for Windows (Wispr Flow style). Windows companion to the Android
app at github.com/rohitsinghcoder/Murmur; keep behaviour in parity with its Kotlin sources.

## Run
- `.venv\Scripts\python -m murmur`: tray app. `python -m murmur.console`: terminal test.
- `python bench.py`: speed test. `python -m pytest`: tests.
- Model is not in git: `scripts/fetch_model.py` downloads it into `models/`.
- Only one instance runs (named mutex `Local\MurmurDictation`); quit from the tray before
  relaunching.

## Speech model
- NVIDIA Nemotron Speech Streaming EN 0.6B, 560 ms chunks, int8, via sherpa-onnx 1.13.8 on CPU,
  4 threads (6 was slower on a Ryzen 5 4600H). feat_dim 128. Settings mirror `Engine.kt`.

## Layout (`murmur/`)
- `engine.py`: port of `Engine.kt`. `dictation.py`: port of `DictationService.runSession`.
- `cleanup.py`, `numbers.py`: line-for-line ports of `Cleanup.kt`, `Numbers.kt`.
- `hotkey.py`: WH_KEYBOARD_LL hook; Right Ctrl hold / double-tap hands-free / Esc cancel.
  Injected keys are ignored so our own Ctrl+V doesn't retrigger it.
- `inserter.py`: clipboard paste + restore, SendInput Unicode typing fallback.
- `overlay.py`: PySide6 pill; never takes focus. `__main__.py`: `App(QObject)`; background
  threads only emit signals, UI work happens on the Qt thread.

## Windows quirks
- Default hotkey is Right Ctrl because Wispr Flow owns Ctrl+Win.
- Clipboard watchers lock the clipboard for a moment after a write that carries the
  "exclude from history" formats; `inserter._wait_readable` waits before sending Ctrl+V.
- `setup.bat` puts its venv in `%USERPROFILE%\.murmur\venv` and history lives in `~/.murmur`:
  PySide6 nests files 176 chars deep (MAX_PATH), and Microsoft Store Python redirects
  AppData writes into its sandbox. The repo's own `.venv` is for development.
- Windows PowerShell 5.1 reads files as ANSI: don't round-trip source files through
  Get-Content/Set-Content (it garbles "…" and "₹").

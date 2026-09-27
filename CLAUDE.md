# Murmur Desktop

Private, on-device voice typing for Windows (Wispr Flow style). Windows companion to the Android
app at github.com/rohitsinghcoder/Murmur; keep behaviour in parity with its Kotlin sources.

## Run
- `.venv\Scripts\python -m murmur`: tray app. `python -m murmur.console`: terminal test.
- `python bench.py`: speed test. `python -m pytest`: tests.
- Model is not in git: `scripts/fetch_model.py` downloads it into `models/`.
- Only one instance runs; quit from the tray before relaunching a changed version.
- UI check without a screen: render pages/pill states to PNG with `widget.grab()` and
  `WA_DontShowOnScreen`, pointing `history.DIR/FILE` at a temp dir with sample entries.

## Speech model
- NVIDIA Nemotron Speech Streaming EN 0.6B, 560 ms chunks, int8, via sherpa-onnx 1.13.8 on CPU,
  4 threads (6 was slower on a Ryzen 5 4600H). feat_dim 128. Settings mirror `Engine.kt`.

## Layout (`murmur/`)
- `engine.py`: port of `Engine.kt`. `dictation.py`: port of `DictationService.runSession`.
- `cleanup.py`, `numbers.py`: line-for-line ports of `Cleanup.kt`, `Numbers.kt`.
- `hotkey.py`: WH_KEYBOARD_LL hook; hold / double-tap hands-free / Esc cancel. Hotkeys are key
  names (`rctrl`, `ctrl`+`shift`+`vk_20`); combo trigger keys are swallowed, Win/Alt combos get
  a dummy key so Start/menus don't open. Also records a new hotkey for Settings. Injected keys
  and AltGr's fake Left Ctrl are ignored.
- `inserter.py`: clipboard paste + restore, SendInput Unicode typing fallback.
- `pill.py`: Wispr-Flow-style bar (no live text by design). Spring-animated; masked so only the
  pill takes the mouse; WindowDoesNotAcceptFocus so clicks don't steal focus.
- `ui/`: main window (Home stats + history, Settings hotkey, About). Always dark.
  `widgets.clear()` hides widgets before deleteLater, or old rows paint over new ones.
- `__main__.py`: `App(QObject)`; background threads only emit signals, UI work happens on the
  Qt thread. Single instance via QLocalServer: a second launch shows the window and exits.
  `--background` starts in the tray (used by the startup shortcut).

## Windows quirks
- Default hotkey is Right Ctrl because Wispr Flow owns Ctrl+Win.
- Clipboard watchers lock the clipboard for a moment after a write that carries the
  "exclude from history" formats; `inserter._wait_readable` waits before sending Ctrl+V.
- `setup.bat` puts its venv in `%USERPROFILE%\.murmur\venv` and history lives in `~/.murmur`:
  PySide6 nests files 176 chars deep (MAX_PATH), and Microsoft Store Python redirects
  AppData writes into its sandbox. The repo's own `.venv` is for development.
- Windows PowerShell 5.1 reads files as ANSI: don't round-trip source files through
  Get-Content/Set-Content (it garbles "…" and "₹").

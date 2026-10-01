# Murmur Desktop

Private, on-device voice typing for Windows (Wispr Flow style). Windows companion to the Android
app at github.com/rohitsinghcoder/Murmur; keep behaviour in parity with its Kotlin sources.

## Run
- `.venv\Scripts\python -m murmur`: tray app. `python -m murmur.console`: terminal test.
- `python bench.py`: speed test. `python -m pytest`: tests.
- Model is not in git: `scripts/fetch_model.py` downloads it into `models/`.
- Only one instance runs; quit from the tray before relaunching a changed version.
- UI check without a screen: show the window off-screen and `view.grab()` it (works for
  WebEngine too), pointing `history.DIR/FILE` at a temp dir with sample entries.

## Speech model
- NVIDIA Parakeet TDT 0.6B v2 int8 (offline, not streaming) via sherpa-onnx 1.13.8 on CPU, 4
  threads, feat_dim 128, model_type nemo_transducer. RTF ~0.085 on a Ryzen 5 4600H. Chosen over the
  Android app's Nemotron streaming model: much better punctuation, and streaming split sentences
  at pauses ("like. Be something"). Live text isn't shown on Windows by design.
- `dictation.Session` hides the latency: background transcription at every 0.3 s pause (used if
  nothing was said after it), and pieces finished at pauses once 5 s is open (the pause needed
  shrinks from 0.35 s to 0.15 s as it grows), each transcribed with 2 s context before and 1.5 s
  after, keeping only tokens timestamped inside the piece; `join` drops punctuation heard on
  both sides of a cut.

## Layout (`murmur/`)
- `engine.py`: loads the model; `tokens()` returns (text piece, seconds) pairs.
  `dictation.py`: mic loop (after `DictationService.runSession`) and `Session`.
- `cleanup.py`, `numbers.py`: line-for-line ports of `Cleanup.kt`, `Numbers.kt`, plus
  `numbers.tidy_digits` for numbers the model already writes as digits (3.30pm, 500 rupees).
- `pipeline.process(text, settings)`: what `Dictation(tidy=...)` runs on a transcript: the
  cleanup steps the switches allow (defaults == `cleanup.tidy`), then `replace.dictionary`,
  `commands.apply` ("new line"/"new paragraph"), `replace.snippets` last (typed verbatim).
  New text processing goes in its own module here, never in cleanup/numbers.
- `settings.py`: keys in DEFAULTS; ones the window may set are in OPTIONS with a validator
  (`Bridge.setOption` -> `App.set_option` -> `App.apply_settings`, which pushes them to history
  retention, sounds, the pill, the mic). `mics.py` (mics by name, MME's 31-char names expanded,
  level `Monitor`), `sounds.py` (QSoundEffect, lazy), `startup.py` (Startup .lnk via PowerShell).
- `hotkey.py`: WH_KEYBOARD_LL hook; hold / double-tap hands-free / Esc cancel. Hotkeys are key
  names (`rctrl`, `ctrl`+`shift`+`vk_20`); combo trigger keys are swallowed, Win/Alt combos get
  a dummy key so Start/menus don't open. Also records a new hotkey for Settings. Injected keys
  and AltGr's fake Left Ctrl are ignored.
- `inserter.py`: clipboard paste, then restores every clipboard format (images, files, rich
  text; GDI-handle formats skipped, EMF copied). SendInput typing is a last resort only: Electron
  apps (Claude, VS Code) take typed keys slowly, in bursts, and can drop some.
- `pill.py`: Wispr-Flow-style bar (no live text by design). Spring-animated; masked so only the
  pill takes the mouse; WindowDoesNotAcceptFocus so clicks don't steal focus. A check mark after
  inserting; messages can take a click action.
- `spacing.py`: space before a dictation when the char before the caret isn't whitespace/opener
  (pure `needs_space`). Read via UI Automation (comtypes, MTA thread, 150 ms limit) or
  EM_GETSEL/WM_GETTEXT for classic Edit; else same window + no typing within 2 min.
- `logfile.py`: `~/.murmur/murmur.log` (rotating 1 MB x 2) plus sys/threading excepthooks. Never
  log dictated text or keystrokes.
- `ui/window.py`: QWebEngineView (off-the-record profile) showing `ui/web` (plain HTML/CSS/JS,
  no build step); `Bridge` is exposed over QWebChannel as `murmur`. `app.js` falls back to sample
  data outside Qt, so `ui/web` can be previewed with `python -m http.server` (`?setup` shows the
  first-run checklist); extend `sampleBridge()` with every new slot. History entries from the
  try-it box (app "Murmur") aren't saved.
- Design: dark zinc neutrals, one accent (#e07a50, burnt orange), Geist + Geist Mono (bundled),
  Phosphor icons (generated `icons.js`), no gradients/glows, no purple. Logo is an M made of five
  waveform bars, middle bar in the accent; drawn in both `style.logo_image` and `app.js` LOGO.
- Themes: settings `theme` is system/light/dark; System follows Windows via Qt's
  `colorSchemeChanged`. Colours are tokens in `style.css` per `[data-theme]`; never hardcode one
  in a rule. Dark shows depth by lightness, light by white surfaces with soft shadows, and uses
  deeper accent/green/red for text. The hands-free bar and logo tile stay dark in both. The
  theme is passed in the page URL so the first frame is right; title bar and tray menu follow.
  A switch crossfades the whole page as one view transition (`switchTheme` in app.js; per-element
  colour transitions went out of step and stuttered). The title bar is part of the page, so it
  fades with it; the frame's dark-mode flag (border) flips halfway (`Bridge.themeShown`).
- `ui/frame.py`: no Windows title bar. WM_NCCALCSIZE keeps the frame (shadow, corners, resize,
  snap) but gives the caption to the page; WM_NCHITTEST makes the page's top strip
  (`TITLE_H` 36 px, minus `BUTTONS_W` for its min/max/close buttons, `.titlebar` in style.css)
  the caption. A native caption can't be kept in step with the page's crossfade: its colour
  reached the screen 0-40 ms apart from the page's, varying with load. Maximised, the page stops
  2 px short of an auto-hidden taskbar's edge: a page covering the whole screen makes Qt treat
  the window as full screen and drop WS_CAPTION etc., which kills Windows' min/max/restore
  animations (and leaves it covering the taskbar on restore).
- `__main__.py`: `App(QObject)`; background threads only emit signals, UI work happens on the
  Qt thread. Single instance via QLocalServer: a second launch shows the window and exits.
  `--background` starts in the tray (used by the startup shortcut).
- Memory: the model is ~670 MB, Chromium's in-process side ~160 MB, the page's renderer process
  ~130 MB. A closed window is released after `RELEASE_WINDOW_MIN` (`MainWindow.release`; Bridge
  keeps its app-signal connections in `_links` so `detach()` can undo them, or lambdas fire at
  the deleted window). With `save_memory`, `Dictation.unload()` drops the model after
  `IDLE_UNLOAD_MIN`; `listen()` preloads it, so it loads (~3.5 s) while you speak.

## Windows quirks
- Default hotkey is Right Ctrl because Wispr Flow owns Ctrl+Win.
- Clipboard watchers lock the clipboard for a moment after a write that carries the
  "exclude from history" formats; `inserter._wait_readable` waits before sending Ctrl+V.
- `setup.bat` puts its venv in `%USERPROFILE%\.murmur\venv` and history lives in `~/.murmur`:
  PySide6 nests files 176 chars deep (MAX_PATH), and Microsoft Store Python redirects
  AppData writes into its sandbox. The repo's own `.venv` is for development.
- Windows PowerShell 5.1 reads files as ANSI: don't round-trip source files through
  Get-Content/Set-Content (it garbles "…" and "₹").
- UIPI drops SendInput into apps of higher integrity (run as administrator): `inserter.paste`
  compares token integrity levels and copies instead. OpenProcessToken(TOKEN_QUERY) works on
  elevated processes from a normal one.
- The laptop mic (Realtek array, MME) opens in 40-75 ms, then fades in over ~300 ms; the stream
  is kept open 10 s after a dictation (`MIC_KEEP_OPEN_S`) so back-to-back ones aren't clipped.
- Classic Win32 Edit controls have no UIA TextPattern (only Value); RichEdit does.

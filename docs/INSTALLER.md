# The Windows installer

`MurmurSetup-<version>.exe` installs Murmur with no Python, no admin rights and no terminal. It's
built with PyInstaller (the app) and Inno Setup (the installer) by one script.

## For users (README section)

> **Install.** Download `MurmurSetup-<version>.exe` from the
> [Releases](https://github.com/rohitsinghcoder/murmur-desktop/releases) page and run it. It
> installs just for you (no admin prompt), downloads the speech model once (460 MB), adds Murmur
> to the Start menu, and can start it with Windows. About 1 GB of disk space in all.
>
> If Windows shows *"Windows protected your PC"*, click **More info → Run anyway**: the installer
> isn't code-signed yet.
>
> **Update.** Run the newer installer; your history, settings and the speech model are kept.
>
> **Uninstall.** Settings → Apps → Murmur → Uninstall. It asks whether to delete your history,
> settings and the speech model too (in `%USERPROFILE%\.murmur`).

Where things go:

| What | Where |
|---|---|
| The app (380 MB) | `%LOCALAPPDATA%\Programs\Murmur` (resources in `_internal\murmur\ui\web` and `_internal\assets`) |
| Speech model (630 MB) | `%USERPROFILE%\.murmur\models\sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8` |
| History, settings, log | `%USERPROFILE%\.murmur` (as before) |
| Shortcuts | Start menu `Murmur`; `Startup\Murmur` (`Murmur.exe --background`) if chosen |

The shortcuts have the same names as `setup.bat`'s, so installing over a `setup.bat` install
replaces them. The Startup shortcut is also Murmur's own "Start with Windows" setting
(`murmur/startup.py`): setup only adds it (never removes one the setting made), and the
uninstaller removes it either way. (A `setup.bat` Murmur still running holds the same single-instance lock; setup asks
to quit it first.)

## Building it

Needs Windows 10/11 x64, Python 3.12 (3.11+ works), and Inno Setup 6:

```bat
winget install -e --id JRSoftware.InnoSetup --scope user
py -3.12 scripts\build_installer.py
```

That, from a clean checkout:

1. creates `build-venv\` (git-ignored) with `installer\requirements-build.txt`: the app's
   packages plus pinned PyInstaller. The repo's `.venv` isn't touched;
2. freezes the app with `installer\murmur.spec` into `dist\Murmur\` (about 2 min);
3. runs the frozen build's self-test if `models\` has the model (`scripts\fetch_model.py`), and
   stops if it fails;
4. compiles `installer\murmur.iss` into `dist\MurmurSetup-<version>.exe` (about 2 min). The
   version is `VERSION` in `murmur/ui/window.py`.

Options: `--no-test`, `--skip-pyinstaller` (reuse `dist\Murmur`). `MURMUR_NO_TRIM=1` builds
without the Qt trimming, to rule it out when something seems missing.

### The self-test

```bat
dist\Murmur\Murmur.exe --selftest [OUT_DIR]
python -m murmur.selftest [OUT_DIR]
```

Starts the real `App` with the keyboard hook and tray icon replaced by stand-ins and the window and
bar rendered off-screen (`WA_DontShowOnScreen`), so it's safe while your own Murmur is running and
never touches its single-instance lock. History/settings/log point at a temp folder with sample
entries. It checks: resources (ui/web, Geist), the model loads, `test_wavs/0.wav` transcribes to
the expected sentence, UI Automation loads through comtypes (`spacing.CaretReader._load`), the
start/stop sounds load through Qt Multimedia, and the page loads with the Qt bridge connected. It writes `selftest.json`, `window.png` and `pill.png`
to OUT_DIR (default `%TEMP%\murmur-selftest`) and exits 0 if everything passed.

The frozen app looks for the model in `~/.murmur/models`; the build script runs the self-test
with `USERPROFILE` pointed at a temp folder holding a junction to `models\`, so nothing is copied
and your own `~/.murmur` isn't used.

### Testing the installer without touching your own setup

Inno Setup resolves `{localappdata}`, the Start menu and Startup folders, and `{%USERPROFILE}`
through `USERPROFILE`, so a silent install with it pointed at a short scratch folder keeps
everything there (only the uninstall entry lands in your real HKCU):

```powershell
$env:USERPROFILE = "$env:TEMP\mh"   # keep it short: the install path must stay under 260 chars
dist\MurmurSetup-0.3.0.exe /VERYSILENT /SUPPRESSMSGBOXES /TASKS=startup /LOG=install.log
& "$env:TEMP\mh\AppData\Local\Programs\Murmur\Murmur.exe" --selftest "$env:TEMP\mst"
& "$env:TEMP\mh\AppData\Local\Programs\Murmur\unins000.exe" /VERYSILENT
```

Don't start the installed `Murmur.exe` without `--selftest` while another Murmur is running: it
would just bring the running one's window up (single instance), or with none running, install its
keyboard hook.

## Decisions

### PyInstaller (one folder), not Nuitka

Measured on this machine (Ryzen 5 4600H, Python 3.12.10, PySide6 6.11.2, PyInstaller 6.22.3,
Nuitka 4.2.2):

| | PyInstaller onedir | Nuitka standalone |
|---|---|---|
| Build time | 110-115 s (plus 130 s Inno Setup) | 714 s (about 3 min of it a one-off MinGW download) |
| App folder | 376 MB trimmed (about 645 MB untrimmed) | 518 MB untrimmed (all translations, debug paks) |
| Launch to window page loaded | 2.2-4.5 s (model loads alongside in 3.4-4.2 s) | 2.2 s (model 3.6-3.9 s) |
| Transcribe sample (7.4 s audio) | RTF 0.09-0.12 | RTF 0.09 |
| QtWebEngine, sherpa-onnx, sounds, comtypes | all pass the self-test | all pass the self-test (once the model was put where it looked) |
| Frozen detection | `sys.frozen` | no `sys.frozen` (sets `__compiled__`), so `engine.MODEL_DIR` needs another check |
| Needs a C compiler | no | yes: downloads a 1.1 GB (unpacked) MinGW64; no MSVC here. The first attempt failed because its cache under the sandboxed AppData path went past MAX_PATH |

Runtime is the same: the time goes into ONNX Runtime and Chromium, both native already, so
compiling Python to C buys nothing. Nuitka costs 6x the build time, a C toolchain on every build
machine, and its own frozen-detection. PyInstaller onedir (not onefile: onefile unpacks 380 MB
to a temp folder on every start) is the well-trodden path for PySide6 + WebEngine.

Trimming (`installer/murmur.spec`, `unused()` and `prune_unlinked_qt()`): no QML modules or Qt
Quick Python modules, no Qt translations (English UI), only `en-US.pak` of Chromium's locales (it
falls back to it: checked with `--lang=de`), no `*.debug.pak`, no dev-tools resources, no
`opengl32sw.dll` (Qt uses Direct3D on Windows), no QML debug/position/virtual-keyboard/PDF
plugins; then Qt DLLs nothing kept links to are dropped (by reading imports with pefile).

### Speech model: downloaded by the installer, into `~/.murmur/models`

- **Why not bundle it** (+460 MB: a ~560 MB installer): every update would weigh 560 MB for a
  model that doesn't change, and LZMA-compressing 630 MB of int8 weights adds minutes to each
  build for almost no gain. (A bundled "offline installer" is easy to add later: a `[Files]`
  entry for the model with `Check: not ModelInstalled`.)
- **Why not on first run in the app**: it needs progress UI in the app and a no-model state in
  every part of it. The installer already has both: Inno Setup's download page shows progress and
  checks the SHA-256, and a failed download leaves you on the Ready page to retry, before
  anything is installed.
- **Why `~/.murmur/models`**: next to history, outside the install folder, so updates and
  reinstalls skip the download (setup checks for the files first). `engine.MODEL_DIR` uses it
  when frozen; running from source still uses `models/`.

The archive (`.tar.bz2` from the sherpa-onnx GitHub release, SHA-256 pinned in `murmur.iss`) is
unpacked with Windows' own `tar.exe` (Windows 10 1803+) into `models\.unpacking` and moved into
place only when complete. Measured (two runs): 78-100 s to download and verify, 62-74 s to
unpack, then 11 s to install the app files.

If the model goes missing later, loading fails and the bar says "Speech model not found in … Run
the Murmur installer again to download it." (re-running setup repairs it). A nicer in-app path
would need a hook in `__main__.py`/the window, which other work owns: on `load_failed` with a
`FileNotFoundError` when frozen, show a "Download the speech model (460 MB)" action that runs
`scripts/fetch_model.py`'s logic on a thread with a progress signal, then calls `App.load` again.

### comtypes in the frozen app

`spacing.CaretReader` calls `comtypes.client.GetModule("UIAutomationCore.dll")`, which generates
wrapper modules into `comtypes.gen` on first use. The spec runs that call at build time (in
`build-venv`) and bundles `comtypes.gen.*`, so the frozen app imports them and writes nothing
(comtypes still creates an empty `%TEMP%\comtypes_cache\Murmur-312`, its fallback, which is
harmless). The self-test checks UI Automation loads.

### Other code that behaves differently frozen

- `sounds.py` and `startup.py` find `assets/` as `Path(__file__).parent.parent / "assets"`, which
  frozen is `_internal\assets`; the spec bundles it there, so no code change was needed.
- `startup.py` (the "Start with Windows" setting) makes a shortcut to `sys.executable` (frozen:
  `Murmur.exe`, as there's no `pythonw.exe` beside it) with arguments `-m murmur --background`.
  That works (the launcher ignores `-m murmur`), but a tidier shortcut would pass only
  `--background` when `sys.frozen`, and use `{app}` rather than `_internal` as its working folder.
  A two-line change in `startup.py`, left to whoever owns it.
- Qt Multimedia (for the sounds) brings FFmpeg (~19 MB). Qt falls back to its Windows Media
  backend without it, which should play WAVs fine, so it could be trimmed (untested; not done).

## Code signing (not done)

Unsigned, the installer and `Murmur.exe` get SmartScreen's "Windows protected your PC" until they
build up download reputation, and some antivirus products are warier of unsigned PyInstaller apps.
To sign:

- **Certificate**: a standard (OV) code-signing certificate, a few hundred dollars a year; since
  2023 its key has to live on a hardware token or in a cloud HSM, so signing happens on the
  machine with the token or through the vendor's cloud tool. EV certificates no longer skip
  SmartScreen's reputation check, so OV is enough. Cheaper routes: Azure Trusted Signing (a
  monthly fee, identity-verified; check it's offered for individuals in your country) or
  SignPath's free plan for open-source projects (signs in CI from a GitHub release build).
- **What to sign**: `dist\Murmur\Murmur.exe` right after PyInstaller (before Inno Setup packs it),
  then the setup and its uninstaller. For the latter, define a sign tool for ISCC, e.g.
  `ISCC /Ssigntool="signtool.exe sign /fd sha256 /tr http://timestamp.digicert.com /td sha256 /a $f" ...`,
  and add `SignTool=signtool` to `[Setup]` in `murmur.iss`: Inno Setup then signs
  `MurmurSetup-*.exe` and `unins000.exe`. `build_installer.py` would take the sign command as
  an option.
- A new certificate still starts with no reputation: the warning fades as people download the
  signed installer. Signing mainly makes it show a publisher name and stops the "unknown
  publisher" framing (and reduces antivirus false positives, which unsigned PyInstaller apps
  sometimes get).

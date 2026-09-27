# Murmur Desktop

Private voice typing for Windows. Hold **Right Ctrl**, speak, let go, and your words are typed
into whatever app you're in. Speech recognition runs entirely on your computer. No internet, no
account, nothing leaves the machine.

The Windows companion to [Murmur for Android](https://github.com/rohitsinghcoder/Murmur), with the
same speech model and the same text cleanup.

- Hold-to-talk from any app; double-tap Right Ctrl for hands-free, Esc to cancel
- Live transcript in a small pill at the bottom of the screen while you speak
- Punctuation and capitals, and "um", "uh" and similar filler words removed
- Writes numbers the way you'd type them: "twenty twenty five" → 2025, "fifty percent" → 50%,
  "three thirty pm" → 3:30 PM, "five hundred rupees" → ₹500
- Your clipboard is put back after pasting, and dictations stay out of Win+V history
- History of everything you've dictated
- English only for now

It uses NVIDIA's Nemotron Speech Streaming model (0.6B parameters, int8) through
[sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx), on the CPU.

## What you need

- Windows 10 or 11, 64-bit
- [Python](https://www.python.org/downloads/) 3.11 or newer (3.12 recommended)
- About 1.5 GB of free disk space, and ~1 GB of RAM while Murmur runs
- Any laptop or desktop CPU from the last several years. On a Ryzen 5 4600H, the text appears
  about 0.2–0.3 s after you let go of the key.

## Install (5 minutes)

**1. Install Python** if you don't have it. Either download Python 3.12 from
[python.org](https://www.python.org/downloads/) and tick **"Add python.exe to PATH"** in the
installer, or open a terminal and run:

```bash
winget install -e --id Python.Python.3.12
```

**2. Get Murmur.** Either clone it:

```bash
git clone https://github.com/rohitsinghcoder/murmur-desktop.git
```

or, without git, click the green **Code** button at the top of this page → **Download ZIP**,
and unzip it somewhere permanent (like `Documents\murmur-desktop`), not your Downloads folder:
Murmur runs from where you put it.

**3. Double-click `setup.bat`** in the folder. It:

- creates a private Python environment for Murmur in `%LOCALAPPDATA%\Murmur` (just for your user; nothing is installed system-wide),
- installs the packages and downloads the speech model (~800 MB in total),
- adds **Murmur** to your Start menu, and asks whether to start it with Windows,
- starts Murmur.

If Windows shows *"Windows protected your PC"*, click **More info → Run anyway**. That appears
for any downloaded script that isn't signed.

**4. Use it.** When the mic icon turns blue in the system tray (bottom-right, maybe under the
**^** arrow), click into any text box, **hold Right Ctrl, speak, and let go**.

Next time, start Murmur from the Start menu. To update later: `git pull` (or download the ZIP
again), then run `setup.bat` again.

<details>
<summary>Manual setup (for developers)</summary>

```bash
git clone https://github.com/rohitsinghcoder/murmur-desktop.git
cd murmur-desktop
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python scripts\fetch_model.py
.venv\Scripts\python -m murmur
```

`fetch_model.py` downloads the
[Nemotron Speech Streaming EN 0.6B, 560 ms, int8](https://github.com/k2-fsa/sherpa-onnx/releases/tag/asr-models)
model (~650 MB) into `models/`. Running with `python` instead of `pythonw` keeps a console
open, which shows any errors.

</details>

## Using it

| Do this | What happens |
|---|---|
| Hold Right Ctrl, speak, release | Text is pasted into the focused app |
| Double-tap Right Ctrl | Hands-free: keep talking without holding; tap once more to finish |
| Esc while listening | Cancel, nothing is typed |
| Right Ctrl + another key | Works as a normal shortcut; dictation is cancelled |

Right-click the tray icon to open your history or quit. History is stored in
`%APPDATA%\Murmur\history.jsonl`.

## Other tools

- `python -m murmur.console`: try dictation in the terminal (Enter to start and stop)
- `python bench.py [file.wav] [-t 4 6]`: how fast the model runs on your machine
- `python -m pytest`: tests for the text cleanup and the hotkey

## Good to know

- **Text is pasted, not typed.** Murmur briefly puts the text on the clipboard, presses Ctrl+V
  and then restores what you had copied (plain text; formatting of copied rich text is dropped).
  If you had an image or files copied, it types the text as keystrokes instead so they're kept.
- **Another dictation app using Ctrl+Win** (like Wispr Flow) doesn't clash; Murmur only uses
  Right Ctrl.
- **Your antivirus might ask about it.** Murmur watches for the Right Ctrl key with a
  system-wide keyboard hook, which some antivirus tools flag. It only reacts to Right Ctrl
  and Esc; nothing you type is recorded, and nothing is sent over the network.

## Troubleshooting

| Problem | Fix |
|---|---|
| Nothing happens when I hold Right Ctrl | Check the tray icon is blue (grey means the model is still loading). Some keyboards have no Right Ctrl; open an issue. |
| The pill says the microphone is unavailable | Settings → Privacy & security → Microphone: turn on **Microphone access** and **Let desktop apps access your microphone**. |
| Words come out wrong | Speak at a normal pace, close to the mic; built-in laptop mics in a noisy room struggle. |
| Text doesn't appear in one particular app | Some apps block pasting. The text is still in your history (tray → Open history). |
| `setup.bat` says packages failed | Install Python 3.12, delete `%LOCALAPPDATA%\Murmur\venv`, run `setup.bat` again. |
| I want to see errors | Quit Murmur, then in a terminal in the Murmur folder run `%LOCALAPPDATA%\Murmur\venv\Scripts\python -m murmur`. |

## Uninstall

Quit Murmur from the tray icon, double-click `uninstall.bat` (removes the shortcuts), then
delete the Murmur folder, `%LOCALAPPDATA%\Murmur` (its Python environment) and `%APPDATA%\Murmur` (your history).

## Project layout

Everything is in `murmur/`:

| File | What it does |
|---|---|
| `engine.py` | Loads the speech model once; `Transcriber` streams audio in and text out |
| `dictation.py` | Records from the mic and transcribes while you speak |
| `hotkey.py` | Global Right Ctrl hold-to-talk via a low-level keyboard hook |
| `inserter.py` | Pastes into the focused app and restores the clipboard |
| `overlay.py` | The listening pill |
| `cleanup.py`, `numbers.py` | Filler-word removal and number formatting (ports of the Android app's) |
| `history.py` | Dictation history |
| `__main__.py` | Tray app that wires it all together |

`setup.bat`, `uninstall.bat` and `scripts/` handle installing, the model download and the
shortcuts.

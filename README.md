# Murmur Desktop

Private voice typing for Windows. Hold **Right Ctrl**, speak, let go, and your words are typed
into whatever app you're in. Speech recognition runs entirely on your computer. No internet, no
account, nothing leaves the machine.

The Windows companion to [Murmur for Android](https://github.com/rohitsinghcoder/Murmur), with the
same text cleanup.

- Hold-to-talk from any app; double-tap Right Ctrl for hands-free, Esc to cancel
- A small bar at the bottom of the screen shows your voice while you speak
- Accurate punctuation and capitals, with "um", "uh" and stutters ("to to") left out; said in the
  middle of a sentence, it carries on in lowercase
- Writes numbers the way you'd type them: "twenty twenty five" → 2025, "fifty percent" → 50%,
  "three thirty pm" → 3:30 PM, "five hundred rupees" → ₹500, "Rs 2,450" → ₹2,450
- Say "new line" or "new paragraph" to start one
- Words: names and jargon Murmur listens for and spells your way ("Kubernetes", "sherpa-onnx"),
  and it learns from the words you correct after a dictation
- Snippets: say "my email", get your address
- Your clipboard is put back after pasting, and dictations stay out of Win+V history
- History of everything you've dictated, searchable, with a count of the time you've saved
- Light and dark themes
- English only for now

It uses NVIDIA's [Parakeet TDT 0.6B v2](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v2) speech model
(int8) through [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx), on the CPU. While you talk,
Murmur transcribes in the background at every pause, so the text is usually ready the moment
you let go.

## What you need

- Windows 10 or 11, 64-bit
- [Python](https://www.python.org/downloads/) 3.11 or newer (3.12 recommended)
- About 2 GB of free disk space, and ~1 GB of RAM while Murmur runs
- Any laptop or desktop CPU from the last several years. On a Ryzen 5 4600H, the text appears
  within about 0.2 s of letting go, even after 15 seconds of talking.

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

- creates a private Python environment for Murmur in `%USERPROFILE%\.murmur` (just for your user; nothing is installed system-wide),
- installs the packages and downloads the speech model (about 1 GB in total),
- adds **Murmur** to your Start menu, and asks whether to start it with Windows,
- starts Murmur.

If Windows shows *"Windows protected your PC"*, click **More info → Run anyway**. That appears
for any downloaded script that isn't signed.

**4. Use it.** When the Murmur icon in the system tray (bottom-right, maybe under the **^**
arrow) turns from grey to the coloured logo, the speech model is ready. Click into any text box,
**hold Right Ctrl, speak, and let go**. The first time, Home shows a short checklist: a mic
check, a box to try the shortcut in, and whether to start with Windows.

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
[Parakeet TDT 0.6B v2, int8](https://github.com/k2-fsa/sherpa-onnx/releases/tag/asr-models)
model (~460 MB) into `models/`. Running with `python` instead of `pythonw` keeps a console
open, which shows any errors.

</details>

## Using it

| Do this | What happens |
|---|---|
| Hold Right Ctrl, speak, release | Text is pasted into the focused app |
| Double-tap Right Ctrl | Hands-free: keep talking without holding; tap once more to finish |
| Click the little bar at the bottom of the screen | Hands-free too; click ■ to finish or ✕ to cancel |
| Esc while listening | Cancel, nothing is typed |
| Right Ctrl + another key | Works as a normal shortcut; dictation is cancelled |
| Say "new line" or "new paragraph" | A line break, or a blank line, in the text |

The bar at the bottom of the screen shows what Murmur is doing: it grows into a black pill with
bars that move with your voice, shimmers while it finishes, and shrinks back when your text is in.
Hover it for a hint, or click it to start dictating hands-free. It steps aside while a
fullscreen video or game is in front; if you'd rather never see it while you're not dictating,
turn off **Show the bar when idle** in Settings.

Right-click the tray icon for **Paste last dictation** (into the app you were in), **Copy last
dictation**, your **Recent** dictations, **Pause Murmur** (the shortcut and the bar stop
dictating until you resume), and **Quit Murmur**.

Open the Murmur window from the Start menu or by clicking the tray icon. **Ctrl+1** to **4**
switch between its pages:

- **Home:** your stats (words, words per minute, streak, and how much faster than typing that
  is), a box to try dictation, and your history grouped by day, with a filter by app. Copy a
  dictation with its copy button (or Enter); right-click it (or use ⋯) to delete it, with a few
  seconds to undo, or to fix a word Murmur got wrong. Search (Ctrl+F) highlights what matches.
  Dictations in the try-it box are practice and aren't saved.
- **Words:**
  - *Words:* names, products and jargon. Murmur listens for them and writes them exactly as you
    gave them ("Kubernetes", "sherpa-onnx"). If it keeps writing one wrong, add what it writes
    as "heard as". With **Learn from my fixes** on, a word you correct after a dictation is
    added here by itself, marked Learned (undo it from the bar).
  - *Snippets:* say a phrase, get your text, even several lines. Phrases of two or more words
    work mid-sentence ("send it to my email"); a single word only works said on its own.
- **Settings:**
  - *Shortcut:* push-to-talk on any key or combo, like Right Alt, F9 or Ctrl + Shift + Space.
  - *General:* start with Windows, which microphone to use (with a test), a soft sound when
    Murmur starts and stops listening, and freeing memory when idle.
  - *Text:* remove filler words and stutters, write numbers as digits, voice commands; each can
    be turned off.
  - *Appearance:* System, Light or Dark theme, and whether the bar shows when idle.
  - *History:* keep it forever, a year, 30 days, or not at all; export it as Markdown or text;
    or clear it.
- **About:** the speech model, a speed test, where your data is kept, and the log.

Closing the window keeps Murmur running in the tray. Quit from the tray icon's menu. History,
settings and the log (`murmur.log`, which never includes what you said) are stored only on your
PC, in `%USERPROFILE%\.murmur`.

## Other tools

- `python -m murmur.console`: try dictation in the terminal (Enter to start and stop)
- `python bench.py [file.wav] [-t 4 6]`: how fast the model runs on your machine
- `python -m pytest`: tests for the text cleanup, words, snippets, voice commands, learning from
  fixes, history, the hotkey and the dictation's piece-by-piece transcription
- `python -m murmur.selftest`: starts the real app off-screen and checks the model, the window
  and the bar (also run on installer builds)

## Good to know

- **Text is pasted, not typed.** Murmur briefly puts the text on the clipboard, presses Ctrl+V
  and then puts back everything you had copied: text, formatting, images, files. Its own text
  stays out of Win+V clipboard history.
- **Another dictation app using Ctrl+Win** (like Wispr Flow) doesn't clash; Murmur only uses
  its own shortcut.
- **Your antivirus might ask about it.** Murmur watches for its shortcut with a system-wide
  keyboard hook, which some antivirus tools flag. It only reacts to the shortcut and Esc;
  nothing you type is recorded, and nothing is sent over the network.
- **Learning from your fixes** reads the text around a dictation for two minutes after pasting
  it, on your PC only, to spot a word you correct. Turn it off on the Words page.

## Troubleshooting

| Problem | Fix |
|---|---|
| Nothing happens when I hold Right Ctrl | Check the tray icon shows the coloured logo (grey means the model is still loading, or Murmur is paused: resume it from the tray menu). Some keyboards have no Right Ctrl; pick another shortcut in Settings. |
| The pill says the microphone is unavailable or silent | Windows Settings → Privacy & security → Microphone: turn on **Microphone access** and **Let desktop apps access your microphone**. With more than one mic, pick the right one in Murmur's Settings. |
| Words come out wrong | Speak at a normal pace, close to the mic; built-in laptop mics in a noisy room struggle. For names and jargon it gets wrong, add them on the Words page (and what it writes instead as "heard as"). |
| Text doesn't appear in one particular app | Some apps block pasting, and apps run as administrator can't be typed into (Murmur copies the text instead). It's still in your history, and in the tray menu under **Copy last dictation**. |
| `setup.bat` says packages failed | Install Python 3.12, delete `%USERPROFILE%\.murmur\venv`, run `setup.bat` again. |
| I want to see errors | About → **Open log**, or open `%USERPROFILE%\.murmur\murmur.log`. |

## Uninstall

Quit Murmur from the tray icon, double-click `uninstall.bat` (removes the shortcuts), then
delete the Murmur folder and `%USERPROFILE%\.murmur` (its Python environment and your history).

## Project layout

Everything is in `murmur/`:

| File | What it does |
|---|---|
| `engine.py` | Loads the speech model once; turns audio into text with word timings |
| `dictation.py` | Records from the mic; transcribes in the background at pauses and stitches long dictations together at word boundaries |
| `hotkey.py` | Global hold-to-talk hotkey (any key or combo) via a low-level keyboard hook |
| `inserter.py` | Pastes into the focused app and restores the clipboard |
| `pill.py` | The floating bar: resting, recording, hands-free and processing states |
| `pipeline.py` | Everything done to a transcript after the model, following the settings |
| `vocabulary.py`, `fixes.py`, `learn.py`, `spell.py` | Words listened for while decoding; learning the words you correct |
| `repeats.py`, `casing.py` | Stutters; capitals (a sentence carried on, a lowercase "i") |
| `spacing.py` | A space between dictations, from what's before the caret |
| `ui/` | The window: an HTML interface (`ui/web`) in a Qt WebEngine view (`window.py`), plus the logo (`style.py`) |
| `cleanup.py`, `numbers.py` | Filler-word removal and number formatting (ports of the Android app's) |
| `replace.py`, `commands.py` | Dictionary and snippets; "new line" and "new paragraph" |
| `history.py`, `settings.py` | Dictation history and settings, in `~/.murmur` |
| `mics.py`, `sounds.py`, `startup.py` | Microphone list and level meter; start and stop sounds; the Startup-folder shortcut |
| `__main__.py` | Tray app that wires it all together |

`setup.bat`, `uninstall.bat` and `scripts/` handle installing, the model download and the
shortcuts. `scripts/make_icon.py`, `scripts/fetch_icons.py` and `scripts/make_sounds.py`
regenerate the app icon, the interface icons and the start and stop sounds.

## Credits

- Speech model: [NVIDIA Parakeet TDT 0.6B v2](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v2)
  (CC-BY-4.0), run with [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) (Apache-2.0)
- Typeface: [Geist and Geist Mono](https://github.com/vercel/geist-font) (SIL Open Font License,
  see `murmur/ui/web/fonts/OFL.txt`)
- Icons: [Phosphor Icons](https://phosphoricons.com) (MIT)

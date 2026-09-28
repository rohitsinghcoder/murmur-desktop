"""Benchmarks candidate speech models for more languages (see docs/LANGUAGES.md).

    python scripts/bench_models.py fetch parakeet-v3 nemotron-3.5     # test clips + models
    python scripts/bench_models.py run parakeet-v3 --lang auto        # one model, one process
    python scripts/bench_models.py all                                # all runs, one after another
    python scripts/bench_models.py report                             # table from models/results
    python scripts/bench_models.py samples hi_142626.wav ...          # outputs next to references

Models are sherpa-onnx release packages unpacked into models/ (not in git). Test clips go in
models/clips/ with references in models/clips/refs.json (the list is docs/languages-clips.json),
plus the sherpa-onnx language-ID test wavs. Each model runs in its own process, so its peak RAM
(peak working set) is its own. Times are after a warm-up decode, with 4 threads, one clip at a
time like the app.
"""
import argparse
import ctypes
import json
import re
import subprocess
import sys
import time
import unicodedata
from ctypes import wintypes
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"
CLIPS = MODELS / "clips"
LID = MODELS / "spoken-language-identification-test-wavs"
RESULTS = ROOT / "models" / "results"
SR = 16000
THREADS = 4

# Clips per language group. "hi" = Hindi read speech (Kathbath, Common Voice, NPTEL),
# "hinglish" = Hindi lectures with English terms (references mix Devanagari and Latin),
# "en" = LibriSpeech + sherpa's en.wav, "en-tts" = Windows SAPI voices, "en-in" = Indian English,
# "eu" = one clip per European language (no reference; eyeballed).
EU = ["de-german", "es-spanish", "fr-french", "it-italian", "nl-dutch", "po-polish",
      "pt-portuguese", "ru-russian", "sv-swedish", "uk-ukrainian", "cs-czech", "ro-romanian"]


def clip_set() -> dict[str, list[Path]]:
    refs = json.loads((CLIPS / "refs.json").read_text("utf-8"))
    groups: dict[str, list[Path]] = {}
    for name, r in refs.items():
        groups.setdefault(r["lang"], []).append(CLIPS / name)
    groups["en"] = sorted(groups.get("en", [])) + [CLIPS / "en.wav"]
    groups["hi"].append(LID / "hi-hindi.wav")
    groups["eu"] = [LID / f"{n}.wav" for n in EU]
    return groups


RELEASE = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
PACKAGES = {
    "parakeet-v2": "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8",
    "parakeet-v3": "sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8",
    "nemotron-3.5": "sherpa-onnx-nemotron-3.5-asr-streaming-0.6b-1120ms-int8-2026-06-11",
    "omnilingual-300m": "sherpa-onnx-omnilingual-asr-1600-languages-300M-ctc-v2-int8-2026-02-05",
    "whisper-turbo": "sherpa-onnx-whisper-turbo",
    "canary-180m": "sherpa-onnx-nemo-canary-180m-flash-en-es-de-fr-int8",
    "qwen3-asr-0.6b": "sherpa-onnx-qwen3-asr-0.6B-int8-2026-03-25",
    "dolphin-base": "sherpa-onnx-dolphin-base-ctc-multi-lang-int8-2025-04-02",
}
ROWS = "https://datasets-server.huggingface.co/rows?dataset={}&config={}&split={}&offset={}&length=1"


def _untar(name: str):
    import tarfile
    import urllib.request
    if (MODELS / name).exists():
        return
    MODELS.mkdir(exist_ok=True)
    arc = MODELS / f"{name}.tar.bz2"
    print("downloading", arc.name, flush=True)
    urllib.request.urlretrieve(RELEASE + arc.name, arc)
    with tarfile.open(arc, "r:bz2") as t:
        t.extractall(MODELS, filter="data")
    arc.unlink()


def fetch(models: list[str]):
    """Test clips (Hugging Face datasets-server, sherpa-onnx test wavs, Windows TTS) and models."""
    import urllib.request
    CLIPS.mkdir(parents=True, exist_ok=True)
    clips = json.loads((ROOT / "docs" / "languages-clips.json").read_text("utf-8"))
    for name, c in clips.items():
        if (CLIPS / name).exists():
            continue
        src = c["source"]
        if src.startswith("agarwalayushi/hinglish row"):
            url = ROWS.format("agarwalayushi/hinglish", "default", "train", int(src.split()[2]))
        elif src.startswith("hf-internal-testing/librispeech_asr_dummy"):
            url = ROWS.format("hf-internal-testing/librispeech_asr_dummy", "clean", "validation",
                              int(src.split()[1]))
        else:  # Windows SAPI voice
            voice = "David" if name.endswith(("1.wav", "3.wav")) else "Zira"
            ps = ("Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis."
                  f"SpeechSynthesizer; $s.SelectVoice('Microsoft {voice} Desktop'); $f = New-Object "
                  "System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, 'Sixteen', 'Mono'); "
                  f"$s.SetOutputToWaveFile('{CLIPS / name}', $f); $s.Speak('{c['ref'].replace(chr(39), chr(39) * 2)}')")
            subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)
            continue
        row = json.load(urllib.request.urlopen(url, timeout=60))["rows"][0]["row"]
        urllib.request.urlretrieve(row["audio"][0]["src"], CLIPS / name)
        print("got", name, flush=True)
    (CLIPS / "refs.json").write_text(json.dumps(clips, ensure_ascii=False, indent=1), "utf-8")
    if not (CLIPS / "en.wav").exists():
        urllib.request.urlretrieve(RELEASE + "en.wav", CLIPS / "en.wav")
    _untar(LID.name)
    for m in models:
        _untar(PACKAGES[m])


def read(path: Path) -> np.ndarray:
    audio, sr = sf.read(path, dtype="float32", always_2d=True)
    audio = audio.mean(axis=1)
    if sr != SR:
        n = int(len(audio) * SR / sr)
        audio = np.interp(np.linspace(0, len(audio), n, endpoint=False), np.arange(len(audio)), audio)
    return audio.astype(np.float32)


# --- memory (Windows) ---------------------------------------------------------------------------

class _PMC(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]


def memory_mb() -> tuple[int, int]:
    """(peak working set, peak private bytes) of this process in MB."""
    pmc = _PMC()
    pmc.cb = ctypes.sizeof(pmc)
    k32 = ctypes.WinDLL("kernel32")
    psapi = ctypes.WinDLL("psapi")
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PMC), wintypes.DWORD]
    psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb)
    return pmc.PeakWorkingSetSize >> 20, pmc.PeakPagefileUsage >> 20


# --- models -------------------------------------------------------------------------------------

def _f(d: Path, prefix: str) -> str:
    files = sorted(d.glob(f"{prefix}*.onnx"), key=lambda f: 0 if "int8" in f.name else 1)
    return str(files[0])


class Offline:
    """Any sherpa-onnx OfflineRecognizer: decode returns (text, tokens, timestamps, lang)."""

    def __init__(self, rec):
        self.rec = rec

    def decode(self, audio: np.ndarray, lang: str):
        s = self.rec.create_stream()
        s.accept_waveform(SR, audio)
        self.rec.decode_stream(s)
        r = s.result
        return r.text, list(r.tokens), list(r.timestamps), getattr(r, "lang", "")


class Nemotron:
    """Nemotron 3.5 is a streaming model: feed the whole clip at once, then flush. The language
    is a per-stream option ("hi", "en", ..., or "auto")."""

    def __init__(self, d: Path):
        import sherpa_onnx
        self.rec = sherpa_onnx.OnlineRecognizer.from_transducer(
            tokens=str(d / "tokens.txt"), encoder=_f(d, "encoder"), decoder=_f(d, "decoder"),
            joiner=_f(d, "joiner"), num_threads=THREADS, sample_rate=SR, feature_dim=128,
            decoding_method="greedy_search", model_type="nemo_transducer", provider="cpu")

    def decode(self, audio: np.ndarray, lang: str):
        s = self.rec.create_stream()
        if lang and lang != "none":
            s.set_option("language", lang)
        # Without some silence first, the first word or two are often lost (tested: "दोस्तों",
        # "यदि नहीं", "अब अगर" dropped at the start of clips that begin with speech).
        s.accept_waveform(SR, np.zeros(int(LEAD_S * SR), np.float32))
        s.accept_waveform(SR, audio)
        s.accept_waveform(SR, np.zeros(int(1.5 * SR), np.float32))  # flush the last chunk
        s.input_finished()
        while self.rec.is_ready(s):
            self.rec.decode_stream(s)
        r = self.rec.get_result_all(s)
        return r.text, list(r.tokens), [max(0.0, t - LEAD_S) for t in r.timestamps], ""


LEAD_S = 0.5


def build(name: str, lang: str):
    import sherpa_onnx as so
    O = so.OfflineRecognizer
    if name in ("parakeet-v2", "parakeet-v3"):
        d = MODELS / f"sherpa-onnx-nemo-parakeet-tdt-0.6b-{name[-2:]}-int8"
        if name == "parakeet-v2" and not d.exists():  # use the main checkout's copy (read-only)
            d = ROOT.parents[2] / "models" / d.name if ROOT.parent.name == "worktrees" else d
        return Offline(O.from_transducer(
            encoder=_f(d, "encoder"), decoder=_f(d, "decoder"), joiner=_f(d, "joiner"),
            tokens=str(d / "tokens.txt"), num_threads=THREADS, sample_rate=SR, feature_dim=128,
            model_type="nemo_transducer", decoding_method="greedy_search", provider="cpu"))
    if name == "nemotron-3.5":
        return Nemotron(next(MODELS.glob("sherpa-onnx-nemotron-3.5-asr-streaming-0.6b-1120ms-int8*")))
    if name.startswith("whisper-"):
        d = MODELS / f"sherpa-onnx-{name}"
        size = name.split("-", 1)[1]
        return Offline(O.from_whisper(
            encoder=str(d / f"{size}-encoder.int8.onnx"), decoder=str(d / f"{size}-decoder.int8.onnx"),
            tokens=str(d / f"{size}-tokens.txt"), language="" if lang == "auto" else lang,
            task="transcribe", num_threads=THREADS, enable_token_timestamps=True))
    if name == "omnilingual-300m":
        d = next(MODELS.glob("sherpa-onnx-omnilingual-asr-1600-languages-300M-ctc-v2-int8*"))
        return Offline(O.from_omnilingual_asr_ctc(
            model=_f(d, "model"), tokens=str(d / "tokens.txt"), num_threads=THREADS))
    if name == "canary-180m":
        d = MODELS / "sherpa-onnx-nemo-canary-180m-flash-en-es-de-fr-int8"
        src = "en" if lang == "auto" else lang
        return Offline(O.from_nemo_canary(
            encoder=_f(d, "encoder"), decoder=_f(d, "decoder"), tokens=str(d / "tokens.txt"),
            src_lang=src, tgt_lang=src, num_threads=THREADS))
    if name == "qwen3-asr-0.6b":
        d = next(MODELS.glob("sherpa-onnx-qwen3-asr-0.6B-int8*"))
        return Offline(O.from_qwen3_asr(
            conv_frontend=_f(d, "conv_frontend"), encoder=_f(d, "encoder"), decoder=_f(d, "decoder"),
            tokenizer=str(d / "tokenizer"), num_threads=THREADS, max_new_tokens=256))
    if name == "dolphin-base":
        d = next(MODELS.glob("sherpa-onnx-dolphin-base-ctc-multi-lang-int8*"))
        return Offline(O.from_dolphin_ctc(model=_f(d, "model"), tokens=str(d / "tokens.txt"),
                                          num_threads=THREADS))
    raise SystemExit(f"unknown model {name}")


def model_size_mb(name: str) -> int:
    pats = {"parakeet-v2": "*parakeet-tdt-0.6b-v2-int8", "parakeet-v3": "*parakeet-tdt-0.6b-v3-int8",
            "nemotron-3.5": "*nemotron-3.5*", "omnilingual-300m": "*omnilingual*",
            "canary-180m": "*canary*", "qwen3-asr-0.6b": "*qwen3-asr*", "dolphin-base": "*dolphin-base*"}
    pat = pats.get(name, f"sherpa-onnx-{name}")
    dirs = list(MODELS.glob(pat)) or list((ROOT.parents[2] / "models").glob(pat))
    # Only the files the app would load (int8 where there is a choice).
    total = 0
    for d in dirs:
        onnx = list(d.glob("*.onnx"))
        int8 = [f for f in onnx if "int8" in f.name]
        total += sum(f.stat().st_size for f in (int8 or onnx))
        total += sum(f.stat().st_size for f in d.rglob("*") if f.is_file()
                     and f.suffix != ".onnx" and "test_wavs" not in f.parts and f.suffix != ".wav")
    return total >> 20


# --- running ------------------------------------------------------------------------------------

LANG_OF = {"hi": "hi", "hinglish": "hi", "en": "en", "en-tts": "en", "en-in": "en", "eu": "auto"}


def run(name: str, lang_mode: str, groups: list[str]):
    """lang_mode: "auto" (model decides) or "forced" (the clip group's language)."""
    t0 = time.perf_counter()
    rec = build(name, "auto" if lang_mode == "auto" else "hi")
    load_s = time.perf_counter() - t0
    rec.decode(np.zeros(SR, np.float32), "auto")  # warm-up
    sets = clip_set()
    rows = []
    forced_recs = {}
    for g in groups:
        for wav in sets[g]:
            lang = "auto" if lang_mode == "auto" else LANG_OF[g]
            if lang == "auto" and g == "eu" and lang_mode == "forced":
                lang = wav.stem.split("-")[0].replace("po", "pl")
            r = rec
            # Whisper and Canary take the language at construction.
            if lang_mode == "forced" and name.startswith(("whisper", "canary")):
                if lang not in forced_recs:
                    forced_recs[lang] = build(name, lang)
                    forced_recs[lang].decode(np.zeros(SR, np.float32), lang)
                r = forced_recs[lang]
            audio = read(wav)
            t = time.perf_counter()
            text, toks, ts, detected = r.decode(audio, lang)
            took = time.perf_counter() - t
            rows.append({"group": g, "clip": wav.name, "secs": len(audio) / SR, "took": took,
                         "text": text.strip(), "n_tokens": len(toks), "n_timestamps": len(ts),
                         "ts_monotonic": all(a <= b for a, b in zip(ts, ts[1:])),
                         "ts_last": ts[-1] if ts else None, "detected": detected,
                         "tokens_sample": toks[:12]})
            print(f"{wav.name}: {len(audio) / SR:.1f}s in {took * 1000:.0f} ms  {text.strip()[:100]}",
                  flush=True)
    peak_ws, peak_priv = memory_mb()
    out = {"model": name, "lang_mode": lang_mode, "load_s": load_s, "peak_ws_mb": peak_ws,
           "peak_private_mb": peak_priv, "size_mb": model_size_mb(name), "rows": rows,
           "extra_recognizers": len(forced_recs)}
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / f"{name}__{lang_mode}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), "utf-8")


# --- scoring ------------------------------------------------------------------------------------

def normalise(s: str) -> list[str]:
    s = unicodedata.normalize("NFC", s).lower()
    s = re.sub(r"[।॥|.,?!;:\"“”‘’()\[\]{}<>]", " ", s)
    s = s.replace("-", " ").replace("'", "")
    return s.split()


def edits(a: list, b: list) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def refs() -> dict[str, str]:
    return {k: v["ref"] for k, v in json.loads((CLIPS / "refs.json").read_text("utf-8")).items()}


def report():
    sys.path.insert(0, str(ROOT))
    from murmur import cleanup  # English numbers to digits, as the app shows them

    R = refs()
    lines = []
    for f in sorted(RESULTS.glob("*.json")):
        d = json.loads(f.read_text("utf-8"))
        by: dict[str, list] = {}
        for row in d["rows"]:
            by.setdefault(row["group"], []).append(row)
        for g, rows in by.items():
            secs = sum(r["secs"] for r in rows)
            took = sum(r["took"] for r in rows)
            we = wn = ce = cn = 0
            for r in rows:
                ref = R.get(r["clip"])
                if ref is None:
                    continue
                hyp = r["text"]
                if g.startswith("en"):  # "three thirty" and "3.30" should both count as right
                    ref, hyp = cleanup.tidy(ref.lower()), cleanup.tidy(hyp)
                    ref, hyp = (re.sub(r"(\d)[.:\s](\d\d)\b", r"\1:\2", x).replace("%", " percent")
                                for x in (ref, hyp))
                a, b = normalise(ref), normalise(hyp)
                we += edits(a, b)
                wn += len(a)
                ce += edits(list("".join(a)), list("".join(b)))
                cn += len("".join(a))
            wer = f"{100 * we / wn:.1f}" if wn else "-"
            cer = f"{100 * ce / cn:.1f}" if cn else "-"
            ts = all(r["n_timestamps"] == r["n_tokens"] and r["n_tokens"] > 0 for r in rows if r["text"])
            texts = [r["text"] for r in rows if r["text"]]
            punct = sum(bool(re.search(r"[,.?!।]", t)) for t in texts)
            empty = sum(not r["text"] for r in rows)
            lines.append(f"| {d['model']} | {d['lang_mode']} | {g} | {len(rows)} | {secs:.0f} | "
                         f"{took / secs:.3f} | {wer} | {cer} | {punct}/{len(texts)} | {empty} | "
                         f"{'yes' if ts else 'no'} | {d['load_s']:.1f} | {d['peak_ws_mb']} | {d['size_mb']} |")
    print("| model | language | clips | n | audio s | RTF | WER % | CER % | punctuated | empty | "
          "token ts | load s | peak RAM MB | size MB |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    print("\n".join(lines))


def samples(clips: list[str]):
    """Each model's output for the given clips, next to the reference."""
    R = refs()
    results = [json.loads(f.read_text("utf-8")) for f in sorted(RESULTS.glob("*.json"))]
    for clip in clips:
        print(f"\n**{clip}**\n")
        print(f"- reference: {R.get(clip, '(none)')}")
        for d in results:
            for r in d["rows"]:
                if r["clip"] == clip:
                    print(f"- {d['model']} ({d['lang_mode']}): {r['text'] or '(empty)'}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["fetch", "run", "report", "all", "samples"])
    ap.add_argument("clips", nargs="*")
    ap.add_argument("--lang", default="auto", choices=["auto", "forced"])
    ap.add_argument("--groups", default="en,en-tts,en-in,hi,hinglish,eu")
    args = ap.parse_args()
    if args.cmd == "fetch":
        fetch(args.clips)
    elif args.cmd == "run":
        run(args.clips[0], args.lang, args.groups.split(","))
    elif args.cmd == "report":
        report()
    elif args.cmd == "samples":
        samples(args.clips)
    else:
        # Only Nemotron takes a language per stream; for the others "auto" is the only mode that
        # matters for the app (Whisper/Canary take it at load time: one recognizer per language).
        runs = [("parakeet-v2", "auto"), ("parakeet-v3", "auto"), ("nemotron-3.5", "auto"),
                ("nemotron-3.5", "forced"), ("omnilingual-300m", "auto"), ("qwen3-asr-0.6b", "auto"),
                ("dolphin-base", "auto"), ("canary-180m", "auto"), ("whisper-turbo", "auto")]
        for m, mode in runs:
            subprocess.run([sys.executable, __file__, "run", m, "--lang", mode, "--groups", args.groups])


if __name__ == "__main__":
    main()

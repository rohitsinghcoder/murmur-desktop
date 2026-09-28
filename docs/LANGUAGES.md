# More languages for Murmur Desktop: Hindi, Hinglish, European

Research and benchmark, September 2026. Nothing in the app was changed. All numbers were measured
with sherpa-onnx 1.13.8 on the Ryzen 5 4600H, CPU only, 4 threads, int8 models, using
`scripts/bench_models.py` and `scripts/bench_stitch.py`.

## Recommendation

1. **Keep Parakeet TDT 0.6B v2 as the English model.** Parakeet v3 is not a free upgrade. It
   adds 24 European languages with good punctuation at the same speed, but on these clips it made
   about 3x as many English errors (WER 3.0 % vs 1.0 % on LibriSpeech, 18 % vs 15 % on Indian
   English). It also writes times as "3 30", which `numbers.tidy_digits` doesn't turn into
   "3:30", and it turns Hindi speech into Latin-script gibberish.
2. **Add NVIDIA Nemotron 3.5 ASR Streaming 0.6B (1120 ms, int8) as an optional "more languages"
   model.** It is a 453 MB download (650 MB on disk). It handles Hindi well (WER 14 %, CER 4.5 %,
   in Devanagari), 25+ European languages about as well as Parakeet v3, and English only a
   little worse than Parakeet. It gives per-token timestamps and takes a per-stream language
   (`stream.set_option("language", "hi")`, or `"auto"`). The Android app already runs this
   model on the NPU with the same English / Hindi / auto choice, so this keeps the two apps in
   parity. No other offline model sherpa-onnx can run comes close for Hindi at usable speed.
3. **Use a language picker, not auto-detect, and keep one model loaded.** Use English (Parakeet
   v2, the default), Hindi, and "Other language" (Nemotron with the language set, or auto).
   Nemotron's auto-detect heard Indian-accented English as Hindi and wrote it in Devanagari
   ("आई गो टू वर्क देर…"), and it did that on 3 of 8 clips. That rules out auto-detect as a
   default for an Indian user. Each model takes about 0.8 to 0.9 GB of RAM and loads in about
   3 s, so load the other model when the picker changes, not per dictation.
4. **Run Nemotron as a streaming model, not through `dictation.Session`.** Its batch RTF is
   about 0.27, 2.5x slower than Parakeet. The last open piece (5 to 9 s plus context) would then
   take 2 to 3 s after you let go. Fed live as the mic delivers audio, it keeps up while you talk
   (RTF 0.23) and the wait after the stop was **225 to 445 ms**, the same as Parakeet's today.
5. **Hinglish:** no offline model that sherpa-onnx runs writes Hinglish the way people type it
   (Latin script, or English words in Latin). Nemotron in Hindi mode writes the whole utterance
   in Devanagari, English words included ("ट्यूटोरियल", "वेबसाइट"). It hears them correctly, so the
   output is readable, and it is the best offline option today. For mostly-English speech with
   Hindi names or words, the English model already does well ("Okay Rajeshji, Kishoreji, many,
   many thanks."). A Latin-script Hinglish mode would need a model that isn't packaged for
   sherpa-onnx yet (see [Hinglish](#hinglish)).

## Candidates

| Model (sherpa-onnx package) | Languages | Punctuation, case | Token timestamps | Verdict |
|---|---|---|---|---|
| Parakeet TDT 0.6B **v2** int8 (current) | English | yes | yes | Best English. Keep. |
| Parakeet TDT 0.6B **v3** int8 | 25 European incl. English, ru, uk; auto-detect | yes | yes | Good European, slightly worse English, no Hindi |
| **Nemotron 3.5 ASR streaming 0.6B** int8 (80/160/320/560/1120 ms) | 40 locales incl. **hi-IN**, en, 25 European, ar, ja, ko, zh, vi, tr, th, he | yes, but weaker (often no final period) | yes | **Recommended add-on** |
| Omnilingual ASR 300M CTC v2 int8 (Meta) | 1600+ incl. Hindi | **no** (lowercase, no punctuation) | yes | Decent Hindi, unusable for typing |
| Qwen3-ASR 0.6B int8 | 52 incl. Hindi; auto-detect | yes | **no** | Best mixed-script Hinglish, but 1 to 3x slower and 2.2 GB RAM |
| Whisper large-v3-turbo (also tiny to large) | 99 incl. Hindi; auto-detect | yes | only if re-exported with attention outputs | Too slow (RTF 1.0); Hindi broken in 1.13.8 |
| Canary 180M flash int8 | en, de, es, fr only | yes | no | No Hindi; loops on some clips |
| Dolphin base CTC int8 | 40 Asian languages incl. Hindi, **no English** | partial | yes | Out: no English, Hindi WER 48 % |
| Cohere Transcribe 14-lang int8 (1.6 GB) | 14 incl. European, no Hindi | yes | n/a | Not tested: no Hindi, 3x the size |
| AI4Bharat IndicConformer (hi / multilingual) | 22 Indic languages | no | yes (CTC) | Not in the sherpa-onnx releases. Community ONNX exports exist but aren't vetted. Hindi only, no English |
| Oriserve Whisper-Hindi2Hinglish (Swift = base, Apex = turbo) | Hindi to **Latin** Hinglish | ? | no | Not in sherpa format. The only Latin-Hinglish option; follow-up |

Hindi-capable models in sherpa-onnx's `asr-models` release: Nemotron 3.5, Omnilingual, Qwen3-ASR,
Whisper and Dolphin. There is no Hindi Zipformer or Parakeet.

## Test audio

- **en**: 6 LibriSpeech clips (`hf-internal-testing/librispeech_asr_dummy`) and sherpa's `en.wav`.
- **en-tts**: 4 dictation-style sentences read by the Windows SAPI voices (David, Zira), with
  times, money and names. TTS flatters every model; every model except Omnilingual got them
  (nearly) all right.
- **en-in**: 8 Indian-English clips from `agarwalayushi/hinglish` (Mann Ki Baat English and a
  read story).
- **hi**: 8 Hindi clips (AI4Bharat Kathbath, Common Voice 17, NPTEL) plus sherpa's
  `hi-hindi.wav` (no reference).
- **hinglish**: 8 code-mixed clips (Spoken Tutorial and NPTEL lectures). The references write
  Hindi in Devanagari and many English words in Latin ("nested और multilevel if statement").
  This is lecture Hinglish, not chat Hinglish, and a model that writes English words in
  Devanagari is marked wrong on them. WER/CER here only rank models; read the samples.
- **eu**: 12 sherpa language-ID clips (de, es, fr, it, nl, pl, pt, ru, sv, uk, cs, ro). They
  have no references, so they were checked by eye.

The clip list with references and sources is in `docs/languages-clips.json`. Raw outputs and
timings for every clip are in `docs/languages-results.json`. WER/CER lowercase the text and drop
punctuation. English numbers are normalised with `cleanup.tidy` so "three thirty" and "3:30"
match.

## Measurements

RTF is transcription time divided by audio length, measured on a quiet machine (first run). A
second run while other work was running on the machine came out 10 to 50 % slower. Peak RAM is
the process's peak working set with the model loaded and decoding. Size is the files that would
ship, with int8 where there is a choice.

| Model | Size MB | Load s | Peak RAM MB | RTF en | RTF hi | WER en | WER en-in | WER / CER hi | WER / CER hinglish | Punct. (hi) | Timestamps |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Parakeet v2 | 630 | 2.7 | 913 | **0.103** | 0.104 | **1.0** | **14.5** | 101 / 102 (Latin gibberish) | 98 / 86 | n/a | yes |
| Parakeet v3 | 639 | 3.2 | 923 | 0.107 | 0.119 | 3.0 | 18.2 | 101 / 102 (Latin gibberish) | 95 / 83 | n/a | yes |
| **Nemotron 3.5**, language set | 650 | 2.7 | **802** | 0.29 (streamed 0.23) | 0.26 | 4.0 | 13.6 | **14.5 / 4.8** | 44.9 / 44.8 | 3/9 | yes |
| Nemotron 3.5, auto | 650 | 2.9 | 802 | 0.24 | 0.27 | 4.0 | 52.7 (Devanagari) | 13.7 / 4.5 | 44.9 / 44.6 | 3/9 | yes |
| Omnilingual 300M | 348 | 1.4 | 822 | 0.20 | 0.21 | 8.9 | 26.4 | 28.2 / 12.2 | 59.3 / 50.7 | 0/9 | yes |
| Qwen3-ASR 0.6B | 899 | 6.0 | 2219 | 0.36 | **0.93** | 2.0 | 15.5 | 17.7 / 9.5 | 47.7 / **38.5** | 7/9 | **no** |
| Whisper turbo | 988 | 3.2 | 1826 | **1.00** | 1.25 | 4.0 | 20.5* | 94 / 82 (broken) | 97 / 82 | 0/9 | no |
| Canary 180M flash | 197 | 1.9 | 547 | 0.17 | 0.15 | 2.0 | 231 (a loop) | no Hindi | no Hindi | n/a | no |
| Dolphin base | 99 | 0.6 | 465 | 0.04 | 0.04 | 95 (no English) | 100* | 47.6 / 35.7 | 85 / 85 | 4/9 | yes |

\* first 3 en-in clips only (not re-run with the 5 added later).

The en-tts (TTS) set scored 0 % WER for all except Omnilingual (15 %) and Whisper (5 %,
"to m m m m"), so it isn't in the table.

**European (eyeballed, 12 clips):**
- **Parakeet v3**: 12/12 right or nearly, with punctuation and a final full stop on 11/12.
- **Nemotron 3.5**: 12/12 right or nearly, with no final full stop on most, and the same
  output with the language set or on auto.
- **Qwen3 and Whisper**: good.
- **Canary**: translated French and German into English, and romanised Russian.
- **Parakeet v2**: phonetic gibberish.

Nemotron 3.5 lists 40 locales; its token list has tags for bg, cs, da, de, el, et, fi, fr, hu,
hr, it, lt, lv, nl, pl, pt-BR/PT, ro, ru, sk, sl, sv, uk, ar, en-GB/US, es-ES/US, fr-CA, he, hi,
ja, ko, nb/nn, th, tr, zh and vi. NVIDIA's own FLEURS WER at 1120 ms is en 7.9, hi 6.8, es 4.1,
de 8.3 and fr 9.0.

### Sample outputs

Hindi, Kathbath `hi_142626`: "जाहिर है जब सहारा खतरे में है तो उसके उपभोक्ता भी खतरे में होंगे"
- Nemotron: जाहिर है जब सहारा खतरे में है तो उसकी उपभोक्ता भी खतरे में होंगे। (1 word off)
- Qwen3: exact. Omnilingual: उपभोकता (1 letter off), no punctuation.
- Parakeet v2: "Jahir hai, jab sahara katre me hai, to uski up bhogta bi katre me hungi."
- Whisper turbo: "ाहिर है  सहारा तरे में" (letters lost: sherpa-onnx issue #3964, fixed by PR #3965 on
  2026-09-20, after 1.13.8)

Hindi, Common Voice `hi_40751`: "गुलदान टूट कर चूर-चूर हो गया"
- Nemotron: गुलदान टूटकर चूर चूर हो गए
- Qwen3: गुल्दांत टूट कर चूर-चूर हो गए.
- Omnilingual: गुलतान टूट क छू छूर होे

Hindi, `hi-hindi.wav` (sherpa): Nemotron "हर कोई दुनिया को बदलने की सोचता है, लेकिन कोई खुद को
बदलने की सोचता ही नहीं". Whisper auto-detected Urdu and wrote it in Urdu script.

Hinglish `hinglish_468625`: "Acceleration phase और dive phase बाद में जुड़ेंगे लेकिन मुख्य रूप से क्रूज़ और लोयटर
रहेगा यानी कि मुख्य रूप से रेंज और इंड्योरेन्स"
- Nemotron (hi): एक्सेलरेशन फेस और डाइव फेस बाद में जुड़ेंगे लेकिन मुख्य रूप से क्रूज और लॉयटर रहेगा यानी कि मुख्य रूप
  से रेंज और इंड्योरेंस
- Qwen3: Acceleration phase और dive phase बाद मिल जाएंगे। रेखेन मुख्य रूप से cruise और loiter रहेगा। यानी की
  मुख्य रूप से range और endurance.
- Parakeet v2: Acceleration phase or dive phase bar nu juring. They can move cruise or loiter. And
  range or endurance.

Hinglish `hinglish_20375`: "variable एक पहचानकर्ता है जो value संदर्भित करता है awk userdefined variables और builtin
variables दोनों को supports करता है"
- Nemotron: वेरिएबल एक पहचान करता है जो वैल्यू संदर्भित करता है और यूजर डिफाइंड वेरिएबल्स और बिल्ट इन वेरिएबल्स दोनों को
  सपोर्ट कर…
- Qwen3: Variable, एक पहचान करता है, जो value, अंदर भेद करता है, और user defined variables और built in
  variables दोनों को support करता है.

Indian English `en-in_224125` (8 s, a story read aloud):
- Parakeet v2/v3: "I go to work there each day, so that he may learn to help the carpenters, for I
  am no longer young and strong."
- Nemotron, language en: same words, no final full stop.
- Nemotron, auto: "आई गो टू वर्क देर ईच डे सो दैट ही मे लर्न टू हेल्प द कर्पर्स, …"

Indian English `en-in_244503` "Got an opportunity to talk to you": Parakeet v3 "Got an
opportunity to doctor." Everyone else was right.

English TTS `en_tts_1` "…at three thirty? I have a doctor's appointment in the morning.":
- Parakeet v2: "at 3.30?" (made "3:30" by `tidy_digits`)
- Parakeet v3: "at 3 30?" (left as is)
- Nemotron: "at three thirty?  I have … morning" (two spaces, no full stop; `numbers.format`
  makes it 3:30)

## Parakeet v3 vs v2 on English

The two are about the same speed (RTF 0.107 vs 0.103), size, RAM and timestamps. Word start
times were within 0.24 s of v2's, so `Session` works unchanged. On these clips v3 was worse at
English:
- LibriSpeech: 3 wrong words vs 1. "Rugado", "Middle Forest", and it lost the capitals in
  "Great Domed Cavern".
- Indian English: 18.2 vs 14.5 % WER. It wrote "Got an opportunity to doctor" and "Okay, Raji,
  Kishour G" where v2 wrote "Rajeshji, Kishoreji".
- Formatting: v3 writes "3 30" (v2: "3.30") and "12%" (v2: "12 percent"), and splits sentences
  more often ("Revenue grew by 12%. But costs went up too.").

NVIDIA's own numbers agree: Open ASR leaderboard average WER is 6.05 for v2 and 6.34 for v3,
and LibriSpeech test-clean is 1.69 vs 1.93. v3 is the right model for a European user. It
shouldn't replace v2 for English, the main use.

## Integration

### Picker vs auto-detect
- **Parakeet v3** auto-detects, but only among its 25 European languages. Hindi speech comes
  out as romanised nonsense, so v3 can't be the "auto" model for an Indian user.
- **Nemotron `auto`** worked for European clips and for Hindi. On Indian-accented English it
  wrote Devanagari transliteration 3 of 8 times (WER 53 % vs 14 % with `en` set).
- **Whisper** detected `hi-hindi.wav` as Urdu.

So: a picker in Settings, **English (default) / हिन्दी Hindi / Auto / a list of Nemotron's other
locales**, stored as `language` in `settings.py` (DEFAULTS and OPTIONS). The pill could show a
small EN/HI tag while listening. A hotkey or tray item to flip English and Hindi would help
bilingual users. With the model already loaded that switch is free for Nemotron (it's a
per-stream option), but it costs a ~3 s reload if it switches between Parakeet and Nemotron.

### One model or two
Parakeet v2 peaks at about 0.9 GB and Nemotron at 0.8 GB, so both loaded is about 1.7 GB. The
recommended default is to load only the model the picker needs and reload on change (2.7 to
3.2 s, done in the background with the pill showing "Loading"). Keeping both loaded could be an
option for users who switch often. Nemotron alone could serve English too (WER 4.0 vs 1.0, 13.6
vs 14.5 on Indian English), but punctuation and number formatting are worse. Keep Parakeet for
English.

### Running Nemotron
Treat it as a streaming model (as the Android app does):
- Create one stream per dictation and set `language`.
- Feed each mic block as it arrives and decode while `is_ready`.
- On stop, feed about 1.5 s of silence, call `input_finished()`, decode and read `get_result`.
- Don't reset the stream at pauses; keeping one stream keeps the sentence context.

Measured feeding 50 ms blocks: decode work while talking was 0.21 to 0.25x the speech length,
and the wait after the stop was 232 ms (9 s English), 225 ms (17.6 s Hindi) and 445 ms (16.3 s
Hinglish).

Nemotron quirks to handle:
- **First word dropped** when speech starts right at the beginning of the audio. Clips starting
  with speech lost "दोस्तों", "यदि नहीं", "अब अगर". Prepending 0.5 to 1 s of silence fixed most
  of these, but not all ("आपने" and "तो" were still lost in two clips). Main now keeps the mic
  open between dictations, so real dictations start with a little room noise. Check this with
  real recordings.
- **Spacing and full stops**: two spaces after "?" and "।", and often no full stop at the end.
  A small language-neutral tidy step can collapse the spaces and add the final "." or "।".
- **Numbers are spelled out**, in every language: "twelve percent", "ट्वेल्व पॉइंट जीरो फोर".
  `numbers.format` already handles English words.
- Language tags like `<hi-IN>` are stripped by sherpa-onnx (PR #3671). With `"auto"` there is no
  API to read which language was detected.

If Nemotron did go through `Session` instead, its timestamps work.
`scripts/bench_stitch.py` feeds 30 to 96 s joined recordings through `Session` in 50 ms blocks
and compares the stitched text with the whole recording decoded in one go:

| Model | en (118 words) | en-tts (80) | hi (123) | hinglish (216) |
|---|---|---|---|---|
| Parakeet v3 | 9 word edits | 0 | n/a | n/a |
| Nemotron 3.5 | 6 | 0 | 5 | 27 |

Most of the differences are the whole-recording decode's own errors, not cut errors.

Nemotron timestamps are in 80 ms frames. After subtracting the lead-in silence the harness adds,
they can come out slightly negative, and `Session` then drops the first token. The harness now
clamps them at 0; an engine wrapper would need to do the same.

The trouble is speed. A 5 to 9 s piece plus 3.5 s of context at RTF 0.27 means a 2 to 3 s wait
after the stop.

A side finding: decoding the whole 50 to 96 s recording in one go was clearly worse than the
stitched pieces. With Parakeet v2 it lost punctuation and case, and on the TTS set it dropped a
sentence ("…on Monday.50 and remind Priya"). That supports `Session`'s piece-by-piece design for
Parakeet. The stitching test ran against this branch's older `Session`. The `,,` and `..` it
showed at cuts are what main's `dictation.join` (f43d137) now removes.

### Text clean-up for other languages
`cleanup.py` and `numbers.py` are English, and they damage other languages:

| Input | `cleanup.tidy` output |
|---|---|
| Ich weiß, **er** ist heute nicht da, aber **er** kommt morgen **um** acht. | Ich weiß ist heute nicht da, aber kommt morgen acht. |
| **Er** is een probleem, maar **er** komt een oplossing. | Is een probleem, maar komt een oplossing. |
| Mi serve una mano, **ah**, grazie mille. | Mi serve una mano grazie mille. |

Hindi and Devanagari pass through unchanged. That includes Hindi fillers ("उम्म"), and number
words stay as words.

So `pipeline.process` should take the dictation's language:
- **English** (Parakeet, or Nemotron with `en`): everything as today.
- **Any other language**:
  - Skip `remove_fillers` and `numbers.format`.
  - Keep `numbers.tidy_digits` (digits only, harmless), `replace.dictionary` and
    `replace.snippets`.
  - Run `commands.apply` only for English, until there are equivalents ("नई लाइन", "neue
    Zeile").
  - Add the neutral tidy step (collapse spaces, final full stop; "।" for Hindi).
- **Later, as their own modules** (per CLAUDE.md: not in cleanup/numbers): Hindi fillers (उम्म,
  अं, हम्म), and Hindi number words to digits. Hindi numbers 1 to 99 are irregular, so this is a
  lookup table. Also English number words in Devanagari ("ट्वेल्व" to 12) for Hinglish.

`Session` and the inserter are language-neutral: SendInput Unicode and paste both carry
Devanagari. History, search and word counts work on any script. Words-per-minute counts
whitespace-separated words, which is fine for Hindi.

### Downloads
`scripts/fetch_model.py` would take a model name. The window's first-run checklist or Settings
would offer "Hindi and other languages (450 MB download)". The package is
`sherpa-onnx-nemotron-3.5-asr-streaming-0.6b-1120ms-int8-2026-06-11.tar.bz2`: 453 MB
compressed, 650 MB unpacked, and only encoder/decoder/joiner and tokens.txt are needed. The
Nemotron 3.5 license is OpenMDW-1.1, which allows redistribution. Parakeet v3, if it is ever
offered for European-only users, is 464 MB / 639 MB.

## Hinglish

How Indians type Hinglish (Latin script, "kal meeting hai, please remind kar dena") is not what
any offline model that sherpa-onnx runs produces:
- **Nemotron 3.5 in `hi` mode** hears code-mixed speech well: it recognised the English terms in the
  lecture clips (tutorial, website, variable, phase…). It writes everything in Devanagari. This is readable and fine for
  Hindi chats, but not what a Latin-script Hinglish user wants.
- **Qwen3-ASR** writes the most natural mixed script (English words in Latin, CER 38 % vs
  Nemotron's 45 % against mixed-script references). But it has no timestamps, runs at RTF
  0.8 to 0.9 on Hindi (a 10 s dictation takes 8 to 9 s) and peaks at 2.2 GB. Not usable here
  yet.
- **Parakeet v2/v3** turn Hindi into romanised English-ish words ("Yadi nahi, so tutorials,
  website parjay"). That is not usable for Hindi, but the English model is the best choice
  for *mostly English* speech with Hindi names and words.
- **Whisper Hindi2Hinglish by Oriserve** (Apache-2.0) is the only open model trained to write
  Hindi speech as Latin Hinglish. Apex is fine-tuned from whisper-large-v3-turbo; its own
  model card reports FLEURS WER 29.8 vs 50.8 for the base model. Swift is fine-tuned from
  whisper-base (73 M parameters). Neither is packaged for sherpa-onnx; an unvetted third-party
  export exists on Hugging Face and was not downloaded. Turbo-sized Whisper runs at RTF about
  1.0 on this CPU, so Apex would be too slow. Swift would be fast, but its quality is unknown.

What to do:
1. Ship Nemotron with **Hindi (Devanagari)** now. Tell mostly-English Hinglish speakers to keep
   English.
2. Follow-up spike: export **Oriserve Whisper-Hindi2Hinglish-Swift** to sherpa-onnx's Whisper
   format with attention outputs (`scripts/whisper/export-onnx-with-attention.py`, for token
   timestamps). Benchmark it on real Hinglish dictation as a "Hinglish (Roman)" option.
3. Not recommended: romanising Nemotron's Devanagari by rule. English loanwords come out as
   "tyutoriyal" or "vebsait". A learned transliterator (AI4Bharat IndicXlit) is another model
   to ship.

## What's uncertain

- **Small test sets**: 7 to 9 clips per language group, 12 unreferenced European clips. The
  Hinglish clips are lectures, not chat-style dictation. Differences of one or two words between
  models (Parakeet v3 vs v2, Nemotron vs Parakeet on English) are within noise. The direction
  matches NVIDIA's published numbers.
- **No real mic recordings from the user.** A 10-minute session of the user dictating Hindi,
  Hinglish and English (`bench.py my.wav`) would settle Nemotron's first-word drop and the
  Hinglish script question better than any dataset.
- **Speed numbers moved by 10 to 50 % between runs** because other work was running on the
  machine. Ratios between models were stable.
- Only Nemotron's 1120 ms variant was tested. NVIDIA says 560 ms and below lose some accuracy.
  1120 ms suits dictation, since nothing is shown live.
- Whisper's Hindi output in 1.13.8 is broken by sherpa-onnx issue #3964, fixed in PR #3965
  (merged after 1.13.8). Whisper turbo is still ruled out by speed (RTF 1.0), its hallucination
  loops ("र र र र…", "the way of the way of…") and no timestamps in the stock export.
- Nemotron with `language` set vs `auto` gave the same Hindi and European output here. Auto's
  failure on Indian English is the deciding factor, and it may vary by speaker.

## Reproduce

```
python scripts/bench_models.py fetch parakeet-v3 nemotron-3.5   # clips + models into models/
python scripts/bench_models.py run nemotron-3.5 --lang forced   # one model (own process)
python scripts/bench_models.py all                              # all runs, one after another
python scripts/bench_models.py report                           # the table
python scripts/bench_models.py samples hi_142626.wav            # outputs next to the reference
python scripts/bench_stitch.py parakeet-v2 parakeet-v3 nemotron-3.5
```
Parakeet v2 is read from the main checkout's `models/` when the worktree has none. The rejected
models were deleted after the run; `fetch` takes any name from `PACKAGES` to get them back.

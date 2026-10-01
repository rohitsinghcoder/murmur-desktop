"""Fixes it learns from: after a dictation is pasted, the user may fix a misheard word by hand
("Sherpa Onyx" -> "sherpa-onnx", "Rohid" -> "Rohit"). This finds such fixes, as dictionary
pairs [heard, write] to offer the user (murmur/replace.py).

Pure functions, no I/O:
- find_span(inserted, before, after, now) finds what became of the pasted text in text read back
  from the app later, using the text around it at paste time as anchors.
- corrections(inserted, edited, is_word) compares the two word by word and keeps only the
  changes that look like a misheard word being fixed, not a rewrite, an addition, a style edit
  or a punctuation tweak.

`is_word(w)` says whether w is a real word as written (spell.Speller.is_word wraps Windows'
own spell checker; tests pass a set). It never sees anything but single words.
"""
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Callable

# A token is a run of non-space characters; its core drops the punctuation around a word.
_TOKEN = re.compile(r"\S+")
_EDGE = "\"'“”‘’()[]{}<>.,;:!?…*_~`"
# Letters inside a token that make it a term (sherpa-onnx, Node.js, C++, C#, gpt_4).
_JOINERS = re.compile(r"\w[-.+#_/]\w|\w[+#]+$")

MAX_WORDS = 3  # each side of a fix
MAX_FIXES = 3  # more than this in one dictation is an editing pass, not fixes
MAX_CHANGED = 0.5  # share of the dictation's letters changed other than by fixes: rewritten
MIN_SIMILAR = 0.6  # sound/spelling similarity of heard and write (0..1)


@dataclass(frozen=True)
class Fix:
    heard: str  # as Murmur typed it, e.g. "Sherpa Onyx"
    write: str  # as the user corrected it, e.g. "sherpa-onnx"
    strong: bool  # worth a prompt at once; weak ones wait until seen again
    similarity: float


def _core(token: str) -> str:
    return token.strip(_EDGE)


def _tokens(text: str) -> list[tuple[str, int, int]]:
    """(core, start, end) for each word, with punctuation-only tokens left out."""
    out = []
    for m in _TOKEN.finditer(text):
        core = _core(m.group())
        if core:
            out.append((core, m.start(), m.end()))
    return out


# ---- Finding the pasted text again -------------------------------------------------------------

def _best_split(left: list[str], right: list[str], words: list[str], span_left: bool) -> int:
    """How many of `words` go with `left` (the rest with `right`) so each side reads most like
    its own: where a fixed word ends and words typed next to it begin ("Rohid" vs
    "Rohit See you"). On a tie the span (`left` if span_left) takes fewer words."""
    def score(k):
        a = similarity(" ".join(left), " ".join(words[:k])) if left and k else 0.0
        b = similarity(" ".join(right), " ".join(words[k:])) if right and k < len(words) else 0.0
        return a + b
    return max(range(len(words) + 1), key=lambda k: (score(k), -k if span_left else k))


def _map(opcodes, pattern: list[str], text: list[str], p: int, end: bool) -> int:
    """Where word boundary p of the pattern lands in the text: the first word of the span
    (end=False) or one past its last (end=True). Words typed right at a boundary count as
    outside the span, so text typed after the dictation isn't taken for part of it."""
    for tag, i1, i2, j1, j2 in opcodes:
        if tag != "insert" and ((i1 < p <= i2) if end else (i1 <= p < i2)):
            if tag == "equal":
                return j1 + p - i1
            if tag == "delete":
                return j1
            return j1 + _best_split(pattern[i1:p], pattern[p:i2], text[j1:j2], span_left=end)
    return opcodes[-1][4]


def find_span(inserted: str, before: str, after: str, now: str) -> str | None:
    """The part of `now` that the pasted `inserted` text became, or None if it can't be found
    with confidence (most of it gone, or the anchors and words don't line up).

    `before`/`after`: up to a few dozen characters around the paste when it happened ("" at the
    start/end of the field). `now`: what's there now, read around the same place (bounded).
    """
    ins = [t[0] for t in _tokens(inserted)]
    if not ins:
        return None
    # (A context word cut in half by the read limit just doesn't match; that's harmless.)
    pre = [t[0] for t in _tokens(before)]
    post = [t[0] for t in _tokens(after)]
    pattern = pre + ins + post
    words = _tokens(now)
    if not words:
        return None
    cores = [w[0] for w in words]
    pattern, cores = [w.lower() for w in pattern], [w.lower() for w in cores]
    ops = SequenceMatcher(None, pattern, cores, autojunk=False).get_opcodes()
    p0, p1 = len(pre), len(pre) + len(ins)
    # Enough of the inserted words must still be there, else it's been rewritten or is elsewhere.
    kept = sum(min(i2, p1) - max(i1, p0) for tag, i1, i2, j1, j2 in ops
               if tag == "equal" and i2 > p0 and i1 < p1)
    if kept < max(1, len(ins) // 2):
        return None
    j0, j1 = _map(ops, pattern, cores, p0, end=False), _map(ops, pattern, cores, p1, end=True)
    if j1 <= j0:
        return ""  # all of it deleted
    return now[words[j0][1]:words[j1 - 1][2]]


# ---- Telling misheard-word fixes from other edits ----------------------------------------------

def _letters(text: str) -> str:
    return "".join(c for c in text.lower() if c.isalnum())


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b, autojunk=False).ratio() if a and b else 0.0


def similarity(heard: str, write: str) -> float:
    """How alike two phrases look or sound, 0..1: the better of their letters and their
    Metaphone keys (so "cooper netties"/"Kubernetes" and "sequel"/"SQL" are close)."""
    letters = _similar(_letters(heard), _letters(write))
    sound = _similar("".join(metaphone(w) for w in heard.split()),
                     "".join(metaphone(w) for w in re.split(r"[\s\-.]+", write)))
    return max(letters, sound)


def _is_term(word: str, is_word) -> bool:
    """Vocabulary a dictionary entry is for: not a real word as written, or shaped like a name
    or term (internal capitals, ALL CAPS, joined with - . + #)."""
    if not is_word(word):
        return True
    if any(c.isupper() for c in word[1:]) and not word.isupper():
        return True  # GitHub, iPhone, PyTorch
    if len(word) >= 2 and word.isupper():
        return True  # JSON, SQL, API
    return bool(_JOINERS.search(word)) or any(c.isdigit() for c in word)


def _plain(word: str, is_word) -> bool:
    """An ordinary dictionary word, maybe capitalised for a sentence or in capitals (OK)."""
    return (word.isupper() or word[1:] == word[1:].lower()) and is_word(word.lower())


def _judge(heard: list[str], write: list[str], starts_sentence: bool, is_word) -> Fix | None:
    h, w = " ".join(heard), " ".join(write)
    if any(c.isdigit() for c in h):
        return None  # "3.30pm" -> "3:30 pm": number formatting (numbers.py), not a word
    term = any(_is_term(x, is_word) for x in write)  # "sherpa-onnx", "PyTorch", "JSON"
    if _letters(h) == _letters(w):
        if h.lower() == w.lower():
            # Capitals only: a fix if it gives a name its capitals ("rohit" -> "Rohit",
            # "Iphone" -> "iPhone"), not lowercasing, and not just the start of a sentence.
            gained = {i for i, (x, y) in enumerate(zip(h, w)) if y.isupper() and not x.isupper()}
            if not gained or starts_sentence and gained == {0}:
                return None
        elif not term:
            return None  # "can not" -> "cannot", "e mail" -> "email", "U.S." -> "US": style
        score = 1.0
    else:
        score = similarity(h, w)
        if score < MIN_SIMILAR:
            return None  # a different word, not a misheard one
        if len(heard) == len(write) and all(_plain(x, is_word) for x in heard + write):
            return None  # their -> there, think -> thought: grammar and wording
    # Strong: "Rohid", "netties" aren't words, so a dictionary entry for them can't misfire;
    # nor can one for a phrase that became a term ("get hub" -> "GitHub"). A single real word
    # ("Jason" -> "JSON", "sequel" -> "SQL") would be replaced everywhere: wait to see it again.
    strong = any(not is_word(x) for x in heard) or term and len(heard) > 1
    return Fix(h, w, strong, round(score, 2))


def corrections(inserted: str, edited: str, is_word: Callable[[str], bool]) -> list[Fix]:
    """The misheard-word fixes between what was pasted and what the user left there; none if
    the text was rewritten rather than fixed.

    Read the edited text only once the user has paused (it may be caught mid-word: "Rohi"),
    and only offer a fix found in two reads in a row or in the last one."""
    a, b = _tokens(inserted), _tokens(edited)
    if not a or not b:
        return []
    ac, bc = [t[0] for t in a], [t[0] for t in b]
    ops = SequenceMatcher(None, ac, bc, autojunk=False).get_opcodes()
    replaces = [op for op in ops if op[0] == "replace"]
    if len(replaces) > MAX_FIXES:
        return []  # an editing pass
    # How much changed that isn't a fix, in letters: past MAX_CHANGED it was rewritten.
    def size(words):
        return sum(len(_letters(x)) for x in words)

    other = sum(size(ac[i1:i2]) for tag, i1, i2, _, _ in ops if tag == "delete")
    # Words added in the middle count too; added at either end, they're just more text.
    other += sum(size(bc[j1:j2]) for tag, i1, _, j1, j2 in ops if tag == "insert" and 0 < i1 < len(ac))
    fixes = []
    for _, i1, i2, j1, j2 in replaces:
        # Words typed right after (or before) a fix at the end (start) of the dictation land in
        # the same replace: "Rohid." -> "Rohit. See you tomorrow."
        if i2 == len(ac) and j2 - j1 > i2 - i1:
            j2 = j1 + max(1, _best_split(ac[i1:i2], [], bc[j1:j2], True))
        elif i1 == 0 and j2 - j1 > i2 - i1:
            j1 = j1 + min(j2 - j1 - 1, _best_split([], ac[i1:i2], bc[j1:j2], False))
        fix = None
        if i2 - i1 <= MAX_WORDS and j2 - j1 <= MAX_WORDS:
            # The model capitalises the first word of every dictation and sentence.
            starts = i1 == 0 or inserted[a[i1 - 1][1]:a[i1 - 1][2]].rstrip("\"'”’)")[-1:] in (".", "!", "?")
            fix = _judge(ac[i1:i2], bc[j1:j2], starts, is_word)
        if fix:
            fixes.append(fix)
        else:
            other += size(ac[i1:i2])
    if other > MAX_CHANGED * size(ac):
        return []
    return fixes


# ---- Learning a fix ---------------------------------------------------------------------------

MAX_ENTRIES = 1000  # as settings allows in the dictionary and vocabulary
MAX_REMEMBERED = 1000  # fixes seen once, and fixes undone


def _key(fix: Fix) -> str:
    return f"{fix.heard.lower()} -> {fix.write}"


def learning(settings: dict, fix: Fix) -> tuple[str, list, Callable[[list], list]] | None:
    """What learning `fix` changes: (setting, new value, how to undo it on its value then), or
    None if nothing. Notes in settings["learned"] what it needs to remember.

    A fix of something only Murmur would write ("Rohid", "Sherpa Onyx") goes in the dictionary
    straight away: it can't change anything the user meant. A real word ("Jason" for JSON) could
    be meant elsewhere, so the second time it's fixed, the fix goes in the vocabulary, where it's
    only taken when it's what was heard (vocabulary.py), not swapped in everywhere."""
    memory, key = settings["learned"], _key(fix)
    if key in memory["rejected"]:
        return None
    if not fix.strong:
        seen = memory["seen"]
        if key not in seen and len(seen) >= MAX_REMEMBERED:
            seen.pop(next(iter(seen)))  # the oldest
        seen[key] = seen.get(key, 0) + 1
        if seen[key] < 2:
            return None
        terms = settings["vocabulary"]
        if any(t.lower() == fix.write.lower() for t in terms) or len(terms) >= MAX_ENTRIES:
            return None
        return "vocabulary", terms + [fix.write], lambda now: [t for t in now if t != fix.write]
    pairs, entry = settings["dictionary"], [fix.heard, fix.write]
    same = [p for p in pairs if p[0].lower() == fix.heard.lower()]
    if same == [entry] or len(pairs) >= MAX_ENTRIES:
        return None
    return ("dictionary", [p for p in pairs if p not in same] + [entry],
            lambda now: [p for p in now if p != entry] + same)


def reject(settings: dict, fix: Fix):
    """Never learn `fix` again (the user undid it)."""
    memory = settings["learned"]
    memory["rejected"] = (memory["rejected"] + [_key(fix)])[-MAX_REMEMBERED:]


# ---- Metaphone (Lawrence Philips, 1990), enough for comparing how words sound -------------------

_VOWELS = set("AEIOU")


def metaphone(word: str) -> str:
    w = "".join(c for c in word.upper() if "A" <= c <= "Z")
    if not w:
        return "".join(c for c in word if c.isdigit())
    if w[:2] in ("KN", "GN", "PN", "AE", "WR"):
        w = w[1:]
    if w[0] == "X":
        w = "S" + w[1:]
    elif w[:2] == "WH":
        w = "W" + w[2:]
    out = []
    n = len(w)
    for i, c in enumerate(w):
        prev = w[i - 1] if i else ""
        nxt = w[i + 1] if i + 1 < n else ""
        nxt2 = w[i + 2] if i + 2 < n else ""
        if c == prev and c != "C":
            continue
        if c in _VOWELS:
            if i == 0:
                out.append(c)
        elif c == "B":
            if not (prev == "M" and i == n - 1):
                out.append("B")
        elif c == "C":
            if nxt == "I" and nxt2 == "A" or nxt == "H":
                out.append("K" if prev == "S" else "X")
            elif nxt in ("I", "E", "Y"):
                if prev != "S":
                    out.append("S")
            else:
                out.append("K")
        elif c == "D":
            out.append("J" if nxt == "G" and nxt2 in ("E", "Y", "I") else "T")
        elif c == "G":
            if nxt == "H" and not (i + 2 >= n or nxt2 in _VOWELS):
                continue
            if nxt == "N" and (i + 2 == n or w[i + 2:i + 4] == "ED" and i + 4 == n):
                continue
            if prev == "D" and nxt in ("E", "Y", "I"):
                continue
            out.append("J" if nxt in ("I", "E", "Y") and prev != "G" else "K")
        elif c == "H":
            if prev in ("C", "S", "P", "T", "G"):
                continue
            if prev in _VOWELS and nxt not in _VOWELS:
                continue
            out.append("H")
        elif c == "K":
            if prev != "C":
                out.append("K")
        elif c == "P":
            out.append("F" if nxt == "H" else "P")
        elif c == "Q":
            out.append("K")
        elif c == "S":
            out.append("X" if nxt == "H" or nxt == "I" and nxt2 in ("O", "A") else "S")
        elif c == "T":
            if nxt == "I" and nxt2 in ("O", "A"):
                out.append("X")
            elif nxt == "H":
                out.append("0")
            elif not (nxt == "C" and nxt2 == "H"):
                out.append("T")
        elif c == "V":
            out.append("F")
        elif c == "W" or c == "Y":
            if nxt in _VOWELS:
                out.append(c)
        elif c == "X":
            out.append("KS")
        elif c == "Z":
            out.append("S")
        else:  # F J L M N R
            out.append(c)
    return "".join(out)

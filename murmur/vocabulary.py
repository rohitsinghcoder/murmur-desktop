"""Names and words the user wants heard right: Settings > Vocabulary, plus what the dictionary
writes. They steer the speech model while it decodes ("hotwords"), so it hears "Kubernetes"
where on its own it writes "Cuba or nets".

Hotwords alone also push the terms into speech that only sounds a bit like them ("my colleague"
became "my Claude") and garble words next to them ("Whisper Flow" became "Wisp Airflow"). So:
1. The audio is decoded as usual, and again with the hotwords.
2. `merge` keeps the second decode's words only where they put a term in place of words that
   sound like it; everything else stays as first heard.
Tested on 44 clips (jargon and plain sentences, two voices): jargon written right went from
32/50 to 43/50, and no plain sentence changed. Hotword strength (SCORE) above 1.5 turned
"cloud" into "Claude", which sounds too alike for step 2 to catch. Deciding from the first
decode whether the second was worth it didn't work: with 20 terms, something in most plain
sentences sounded like one ("parked", Parakeet). So a vocabulary doubles the decoding time.

Exact spelling ("sherpa-onnx", "iPhone") is left to the dictionary step: pipeline.process maps
each term to itself, which replace.dictionary matches ignoring case and spaces vs hyphens.
"""
import re
from difflib import SequenceMatcher

Tokens = list[tuple[str, float]]

SCORE = 1.5  # hotword strength, per token (sherpa-onnx hotwords_score)
ALIKE = 0.65  # how alike (`sounds_alike`) a term and what was first heard must be to swap
MAX_TERMS = 1000

_UNSAFE = re.compile(r"[/:]+")  # hotword syntax in sherpa-onnx: "/" separates, ":" sets a score
_SEPARATORS = re.compile(r"[-_.\s]+")
_SOUNDS = [("ph", "f"), ("ck", "k"), ("qu", "kw"), ("q", "k"), ("x", "ks"), ("c", "k"), ("z", "s"),
           ("y", "i"), ("w", "v")]


def _key(text: str) -> str:
    """Letters and digits only, lowercase: "sherpa-onnx" and "Sherpa Onnx" give the same key."""
    return re.sub(r"[\W_]+", "", text.lower())


def sound(text: str) -> str:
    """A rough spelling of how `text` sounds, so "Versal" and "Vercel" come out close."""
    s = re.sub(r"[^a-z]", "", text.lower())
    for a, b in _SOUNDS:
        s = s.replace(a, b)
    s = re.sub(r"(?<=[^aeiou])h", "", s)  # sh, th, dh, gh: the h is barely heard
    return re.sub(r"(.)\1+", r"\1", s)  # doubled letters


def _skeleton(s: str) -> str:
    """A sound() without its vowels, which speech models get wrong the most."""
    return re.sub(r"[aeiou]", "", s) or s[:1]


def sounds_alike(a: str, b: str) -> float:
    """0 to 1: how alike two bits of text sound."""
    sa, sb = sound(a), sound(b)
    return max(SequenceMatcher(None, sa, sb).ratio(),
               SequenceMatcher(None, _skeleton(sa), _skeleton(sb)).ratio() * 0.9)


def terms(settings: dict) -> list[str]:
    """The user's terms: their vocabulary, then what their dictionary writes. One-line text only,
    and each once (ignoring case and spaces vs hyphens)."""
    out, seen = [], set()
    candidates = list(settings.get("vocabulary", ())) + [write for _, write in settings.get("dictionary", ())]
    for term in candidates:
        if "\n" in term:
            continue  # a block of text, not a word
        term = " ".join(term.split())
        if len(term) > 100 or len(_key(term)) < 3 or _key(term) in seen:
            continue  # too short to steer by (it would match too much), or there already
        seen.add(_key(term))
        out.append(term)
    return out[:MAX_TERMS]


def variants(term: str) -> list[str]:
    """How a term might come out of the model: as written, and spoken (words, no hyphens), plain
    and capitalised."""
    term = _UNSAFE.sub(" ", term).strip()
    spoken = " ".join(_SEPARATORS.sub(" ", term).split())
    forms = [term, spoken, spoken[:1].upper() + spoken[1:], " ".join(w[:1].upper() + w[1:] for w in spoken.split())]
    return list(dict.fromkeys(f for f in forms if f))


def _words(tokens: Tokens) -> list[Tokens]:
    """Tokens grouped into words: a piece starting with a space starts a word."""
    words: list[Tokens] = []
    for piece, t in tokens:
        if piece.startswith(" ") or not words:
            words.append([(piece, t)])
        else:
            words[-1].append((piece, t))
    return words


def _text(word: Tokens) -> str:
    return "".join(piece for piece, _ in word).strip()


class Vocabulary:
    def __init__(self, user_terms: list[str]):
        self.terms = user_terms
        self.hotwords = "/".join(v for t in user_terms for v in variants(t))
        self._keys = [_key(t) for t in user_terms]

    def __bool__(self) -> bool:
        return bool(self.terms)

    def _has_term(self, words: list[Tokens]) -> bool:
        heard = _key(" ".join(_text(w) for w in words))
        return any(k in heard for k in self._keys)

    def merge(self, plain: Tokens, steered: Tokens) -> Tokens:
        """`plain` with the words `steered` (decoded with the hotwords) put a term in place of,
        where those sound like what `plain` heard."""
        pw, sw = _words(plain), _words(steered)
        matcher = SequenceMatcher(None, [_key(_text(w)) for w in pw], [_key(_text(w)) for w in sw], autojunk=False)
        out: list[Tokens] = []
        for op, i1, i2, j1, j2 in matcher.get_opcodes():
            take = pw[i1:i2]
            if op != "equal" and self._has_term(sw[j1:j2]):
                heard = " ".join(_text(w) for w in pw[i1:i2])
                if heard and sounds_alike(heard, " ".join(_text(w) for w in sw[j1:j2])) >= ALIKE:
                    take = sw[j1:j2]
            out += take
        return [token for word in out for token in word]

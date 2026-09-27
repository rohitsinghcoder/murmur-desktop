"""The user's dictionary and snippets: phrases swapped for what they should be typed as.

- Dictionary ("sherpa onnx" -> "sherpa-onnx"): fixes names and words the model gets wrong.
  At the start of a sentence an all-lowercase replacement gets a capital, like any word there;
  one with its own capitals (iPhone, GitHub) is written exactly as given.
- Snippets ("my email" -> an address): typed exactly as written, line breaks and all. They
  match anywhere in a dictation, which is what makes them useful mid-sentence ("send it to my
  email"); when the whole dictation is the trigger, the result is just the snippet, without the
  full stop and capital the model added around it.

Both match whole words and phrases only, ignoring case, so "cat" never changes "category". The
words of a phrase may be joined by spaces or hyphens ("e-mail" matches "e mail"), and longer
phrases win over shorter ones that overlap them.
"""
import re

_SEPARATOR = re.compile(r"[\s-]+")
_SENTENCE_END = re.compile(r"(?:^|[.!?]\s+|\n\s*)$")


def _key(phrase: str) -> str:
    return _SEPARATOR.sub(" ", phrase.strip().lower())


def _table(pairs) -> dict[str, str]:
    return {_key(heard): out for heard, out in pairs if _key(heard)}


def _pattern(table: dict[str, str]) -> re.Pattern:
    phrases = sorted(table, key=len, reverse=True)
    alternatives = "|".join(r"[\s-]+".join(re.escape(w) for w in p.split()) for p in phrases)
    return re.compile(rf"(?<!\w)(?:{alternatives})(?!\w)", re.IGNORECASE)


def dictionary(text: str, pairs) -> str:
    table = _table(pairs)
    if not table:
        return text

    def swap(m: re.Match) -> str:
        out = table[_key(m.group(0))]
        starts_sentence = _SENTENCE_END.search(text, 0, m.start()) is not None
        if starts_sentence and m.group(0)[:1].isupper() and out == out.lower():
            out = out[:1].upper() + out[1:]
        return out

    return _pattern(table).sub(swap, text)


def snippets(text: str, pairs) -> str:
    table = _table(pairs)
    if not table:
        return text
    whole = _key(text.strip().rstrip(".!?,;:").strip())
    if whole in table:
        return table[whole]
    return _pattern(table).sub(lambda m: table[_key(m.group(0))], text)

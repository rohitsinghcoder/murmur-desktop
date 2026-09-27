"""Tidies a transcript before it is shown or typed: drops hesitation sounds like "um" and "uh".

Port of the Android app's Cleanup.kt.
"""
import re

from . import numbers

# um, umm, uhm, uh, uhh, ah, ahh, aah, er, erm, hm, hmm, mm. "er" and "ah" are only filler on
# their own; the word boundaries keep "err", "ahead" and similar words intact.
_filler = re.compile(r",?\s*\b(?:u+h*m+|u+h+|a+h+|e+rm*|h+m+|m{2,})\b,?", re.IGNORECASE)
_space_before_punct = re.compile(r"\s+([,.?!])")
_double_comma = re.compile(r",+([,.?!])")
_sentence_start = re.compile(r"([.?!]\s+)([^\W\d_])")
_spaces = re.compile(r"\s{2,}")


def tidy(text: str) -> str:
    """Everything applied to a transcript: fillers out, numbers as digits."""
    return numbers.format(remove_fillers(text))


def remove_fillers(text: str) -> str:
    if not _filler.search(text):
        return text
    cleaned = _filler.sub(" ", text)
    cleaned = _space_before_punct.sub(r"\1", cleaned)
    cleaned = _double_comma.sub(r"\1", cleaned)
    cleaned = _spaces.sub(" ", cleaned).strip().lstrip(",.?! ")
    # Removing a sentence-opening "Um," leaves the next word lowercase.
    cleaned = _sentence_start.sub(lambda m: m.group(1) + m.group(2).upper(), cleaned)
    return cleaned[:1].upper() + cleaned[1:]

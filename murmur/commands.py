"""Spoken formatting: "new line" and "new paragraph" become line breaks.

The model writes the commands as words and punctuates around them as if they were a sentence
("Hello. New line. How are you"). Punctuation before a command belongs to the text before it and
stays; the punctuation the model put after it is dropped, and the next word starts with a
capital, as it would on a new line ("Hello.\\nHow are you").

Said as a noun ("a new line of code", "the new paragraph"), they're left alone: that's when a
word like "a" or "the" comes before, or "of" after.
"""
import re

_COMMAND = re.compile(
    r"[ \t]*(?<![\w'])(?P<cmd>new[ -]?(?:line|paragraph))(?!\w)(?![ \t]+of\b)[.,;:!?]*[ \t]*",
    re.IGNORECASE)
_BEFORE_NOUN = re.compile(
    r"\b(?:a|an|the|this|that|one|another|each|every|my|your|our|their|his|her|its|same)\s*$",
    re.IGNORECASE)
_LINE_START = re.compile(r"(\n)([^\W\d_])")


def apply(text: str) -> str:
    def swap(m: re.Match) -> str:
        if _BEFORE_NOUN.search(text, 0, m.start("cmd")):
            return m.group(0)
        return "\n\n" if m.group("cmd").lower().endswith("paragraph") else "\n"

    out = _COMMAND.sub(swap, text)
    if out == text:
        return text
    return _LINE_START.sub(lambda m: m.group(1) + m.group(2).upper(), out)

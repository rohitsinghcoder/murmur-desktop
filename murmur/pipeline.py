"""Everything done to a transcript before it's typed, following the user's settings.

First cleanup.tidy's steps (the Android app's cleanup; cleanup.py and numbers.py stay
line-for-line ports, and the switches only pick which of their steps run), with stutters going
along with the fillers (repeats.py) and a lowercase "i" made "I" (casing.py). Then the user's
dictionary (vocabulary terms first, written exactly as given), "new line" and "new paragraph",
and snippets.
"""
from . import casing, cleanup, commands, numbers, repeats, replace, vocabulary


def process(text: str, settings: dict) -> str:
    if settings.get("remove_fillers", True):
        # Fillers first: "it, um, it was" is a stutter once the "um" is out.
        text = repeats.remove(cleanup.remove_fillers(text))
    if settings.get("digits", True):
        text = numbers.format(text)
    # Numbers the model already wrote as digits (3.30pm, 500 rupees) are tidied either way:
    # that's formatting, not turning words into digits.
    text = numbers.tidy_digits(text)
    text = casing.capital_i(text)
    # The user's own dictionary after the vocabulary's pairs, so it wins where both have a phrase.
    pairs = [[t, t] for t in vocabulary.terms(settings)] + list(settings.get("dictionary", ()))
    text = replace.dictionary(text, pairs)
    if settings.get("voice_commands", True):
        text = commands.apply(text)
    # Snippets last, so what they type is exactly what the user wrote.
    return replace.snippets(text, settings.get("snippets", ()))

"""Everything done to a transcript before it's typed, following the user's settings.

First cleanup.tidy's steps (the Android app's cleanup; cleanup.py and numbers.py stay
line-for-line ports, and the switches only pick which of their steps run), then the user's
dictionary, "new line" and "new paragraph", and snippets.
"""
from . import cleanup, commands, numbers, replace


def process(text: str, settings: dict) -> str:
    if settings.get("remove_fillers", True):
        text = cleanup.remove_fillers(text)
    if settings.get("digits", True):
        text = numbers.format(text)
    # Numbers the model already wrote as digits (3.30pm, 500 rupees) are tidied either way:
    # that's formatting, not turning words into digits.
    text = numbers.tidy_digits(text)
    text = replace.dictionary(text, settings.get("dictionary", ()))
    if settings.get("voice_commands", True):
        text = commands.apply(text)
    # Snippets last, so what they type is exactly what the user wrote.
    return replace.snippets(text, settings.get("snippets", ()))

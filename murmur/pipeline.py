"""Everything done to a transcript before it's typed, following the user's settings.

With the defaults this is exactly cleanup.tidy (the Android app's cleanup); cleanup.py and
numbers.py stay line-for-line ports, and the switches only pick which of their steps run.
"""
from . import cleanup, numbers


def process(text: str, settings: dict) -> str:
    if settings.get("remove_fillers", True):
        text = cleanup.remove_fillers(text)
    if settings.get("digits", True):
        text = numbers.format(text)
    # Numbers the model already wrote as digits (3.30pm, 500 rupees) are tidied either way:
    # that's formatting, not turning words into digits.
    return numbers.tidy_digits(text)

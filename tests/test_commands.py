import pytest

from murmur import commands


@pytest.mark.parametrize("heard, typed", [
    ("Hello. New line. How are you", "Hello.\nHow are you"),
    ("Hello new line how are you?", "Hello\nHow are you?"),
    ("Dear John, new line, thanks for the notes.", "Dear John,\nThanks for the notes."),
    ("First point. New paragraph. Second point.", "First point.\n\nSecond point."),
    ("Shopping list: new line milk new line eggs", "Shopping list:\nMilk\nEggs"),
    ("One. Newline. Two.", "One.\nTwo."),
    ("New line.", "\n"),
    ("New paragraph", "\n\n"),
    ("Thanks. New line. New line. Rohit", "Thanks.\n\nRohit"),
    ("See you soon new line", "See you soon\n"),
])
def test_commands(heard, typed):
    assert commands.apply(heard) == typed


@pytest.mark.parametrize("text", [
    "I added a new line to the file.",
    "The new paragraph reads better.",
    "It's a new line of products.",
    "Start a new line of code.",
    "New lines everywhere.",
    "The renewline project.",
    "Nothing to do here.",
])
def test_left_alone(text):
    assert commands.apply(text) == text

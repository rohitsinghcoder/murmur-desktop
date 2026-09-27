import pytest

from murmur import cleanup, numbers


@pytest.mark.parametrize("spoken, typed", [
    ("It was twenty twenty five.", "It was 2025."),
    ("Back in nineteen ninety nine", "Back in 1999"),
    ("In twenty oh five", "In 2005"),
    ("About fifty percent of it", "About 50% of it"),
    ("Meet me three thirty pm", "Meet me 3:30 PM"),
    ("Let's go at ten fifteen", "Let's go at 10:15"),
    ("Wake up at seven am", "Wake up at 7 AM"),
    ("See you at three p.m. Then we eat.", "See you at 3 PM. Then we eat."),
    ("It costs five hundred rupees", "It costs ₹500"),
    ("That's twenty five dollars", "That's $25"),
    ("Call nine eight seven six", "Call 9876"),
    ("Open twenty four seven", "Open 24/7"),
    ("About five million people", "About 5 million people"),
    ("Twelve thousand steps", "12,000 steps"),
    ("Pi is three point one four", "Pi is 3.14"),
    ("One hundred and twenty days", "120 days"),
    ("Five lakh rupees saved", "5 lakh rupees saved"),
    ("I have fifteen apples", "I have 15 apples"),
])
def test_numbers_formatted(spoken, typed):
    assert numbers.format(spoken) == typed


@pytest.mark.parametrize("text", [
    "One thing at a time.",
    "Two of them came.",
    "Music from the nineteen sixties.",
    "Pick one two or three.",
    "No numbers here.",
])
def test_numbers_left_alone(text):
    assert numbers.format(text) == text


@pytest.mark.parametrize("spoken, typed", [
    ("Um, so I think, uh, we should go.", "So I think we should go."),
    ("Hmm. Okay.", "Okay."),
    ("That went well. Um, anyway, next.", "That went well. Anyway, next."),
    ("Go ahead, err on the side of caution.", "Go ahead, err on the side of caution."),
])
def test_fillers(spoken, typed):
    assert cleanup.remove_fillers(spoken) == typed


def test_tidy_does_both():
    assert cleanup.tidy("Uh, it's twenty dollars.") == "It's $20."

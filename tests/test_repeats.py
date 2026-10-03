import pytest

from murmur import pipeline, repeats, settings


@pytest.mark.parametrize("said, written", [
    ("I think the the build works.", "I think the build works."),
    ("Send it to to the team.", "Send it to the team."),
    ("They they said so.", "They said so."),
    ("It looks like, like a bug.", "It looks like a bug."),
    ("Send it to, to the team.", "Send it to the team."),
    ("I, I think so.", "I think so."),
    ("It was, like, like a bug.", "It was, like a bug."),
    ("So I I I think so.", "So I think so."),
    ("The the build passed.", "The build passed."),
    ("Come with. with me.", "Come with me."),
    ("Meet me on the. The next day.", "Meet me on the next day."),
    ("I'm I'm not sure.", "I'm not sure."),
    ("One of the first ch chatbots.", "One of the first chatbots."),
    ("It's a pr- problem.", "It's a problem."),
])
def test_stutters_go(said, written):
    assert repeats.remove(said) == written


@pytest.mark.parametrize("said", [
    "That's very, very good.",
    "No no, it's fine.",
    "Bye bye.",
    "I know that that is true.",
    "She had had enough.",
    "What it is is a bug.",
    "Log in in the morning.",
    "Turn it on on Monday.",
    "Hello hello, can you hear me?",
    "Test test.",
    "Look at this. This is the screen.",
    "If you build it, it works.",
    "I told you you were right.",
    "I was on it it just broke.",
    "Fix this this way.",
    "Look at at least two.",
    "Thank you, you were great.",
    "I want this, this and that.",
    "So did I. I really did.",
    "It was like you. You know?",
    "The C compiler.",
    "Ask S Sharma.",
    "My ex expects it.",
    "Go to it.",
    "Itinerary it is.",
    "A an",  # different words
    "it's its own thing",
])
def test_words_said_twice_on_purpose_stay(said):
    assert repeats.remove(said) == said


def test_stutters_go_with_the_fillers_switch():
    said = "Um, I, uh, I was the the best."
    assert pipeline.process(said, settings.DEFAULTS) == "I was the best."
    kept = pipeline.process(said, {**settings.DEFAULTS, "remove_fillers": False})
    assert "I, uh, I" in kept and "the the" in kept

import pytest

from murmur import casing, pipeline, settings
from murmur.casing import capital_i, continue_sentence


@pytest.mark.parametrize("before", ["k ", "nk", "e,", ", ", "5 ", "x;", "— ", "a\u00a0"])
def test_carrying_on_a_sentence_drops_the_capital(before):
    assert continue_sentence("We should ship it.", before) == "we should ship it."


@pytest.mark.parametrize("before", [
    None,  # unknown
    "",  # start of the field
    ". ", "?", "! ", ": ", "\n", "\r\n", "  ", ") ", '" ', "“", "- ",  # a list item
])
def test_a_new_sentence_keeps_it(before):
    assert continue_sentence("We should ship it.", before) == "We should ship it."


@pytest.mark.parametrize("text", [
    "I think so.",
    "I'm in.",
    "Rohit said so.",  # a name
    "Monday works.",
    "May I?",  # a month, too
    "API keys expire.",
    "JSON is fine.",
    "iPhone sales.",
    "New York is big.",  # a name in capitals
    "The Beatles played.",
    "McDonald's is open.",
    "3 more.",
    "\nNext line.",
    "“Quoted” text.",
])
def test_names_and_uncommon_words_keep_their_capital(text):
    assert continue_sentence(text, "d ") == text


@pytest.mark.parametrize("text, written", [
    ("So I think it works.", "so I think it works."),
    ("And then it broke.", "and then it broke."),
    ("It's done.", "it's done."),
    ("Yes.", "yes."),
    ("The build is green.", "the build is green."),
])
def test_common_words_lose_it(text, written):
    assert continue_sentence(text, "d ") == written


def test_the_users_own_words_keep_their_capital():
    assert continue_sentence("Will is here.", "d ", keep=["Will"]) == "Will is here."
    assert continue_sentence("Go is fast.", "d ", keep=["Go", "Rust"]) == "Go is fast."
    assert continue_sentence("Go home.", "d ", keep=["Rust"]) == "go home."


@pytest.mark.parametrize("text, written", [
    ("So i think it's fine.", "So I think it's fine."),
    ("i'll do it, and i'm sure i've said so, i'd say.", "I'll do it, and I'm sure I've said so, I'd say."),
    ("Then i, too, went.", "Then I, too, went."),
    ("and so did i", "and so did I"),
    ("for i in range ten", "for i in range ten"),
    ("That is, i.e. this.", "That is, i.e. this."),
    ("Wi-fi and i/o and pi.", "Wi-fi and i/o and pi."),
    ("Item (i) first.", "Item (i) first."),
])
def test_lowercase_i_is_capital(text, written):
    assert capital_i(text) == written


def test_capital_i_runs_in_the_pipeline():
    assert pipeline.process("So i th also i think.", settings.DEFAULTS) == "So I th also I think."


def test_common_words_are_lowercase_and_never_i():
    assert all(w == w.lower() for w in casing.COMMON)
    assert not {"i", "i'm", "may", "june", "bill"} & casing.COMMON

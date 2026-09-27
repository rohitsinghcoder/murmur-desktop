import pytest

from murmur import replace

WORDS = [["sherpa onnx", "sherpa-onnx"], ["i phone", "iPhone"], ["rohit", "Rohit"],
         ["new york", "New York"], ["new york city", "NYC"], ["c plus plus", "C++"]]


@pytest.mark.parametrize("heard, typed", [
    ("I use sherpa onnx on the CPU.", "I use sherpa-onnx on the CPU."),
    ("I use Sherpa ONNX on the CPU.", "I use sherpa-onnx on the CPU."),
    ("Sherpa onnx runs it. Sherpa-Onnx is fast.", "Sherpa-onnx runs it. Sherpa-onnx is fast."),
    ("Is that an I phone?", "Is that an iPhone?"),
    ("I phone users.", "iPhone users."),
    ("Ask rohit about it.", "Ask Rohit about it."),
    ("Flying to new york city today.", "Flying to NYC today."),
    ("Flying to new york today.", "Flying to New York today."),
    ("Written in c plus plus.", "Written in C++."),
    ("Hello.\nSherpa onnx rocks", "Hello.\nSherpa-onnx rocks"),
    ("sherpa onnx rocks", "sherpa-onnx rocks"),  # the model didn't capitalize it: neither do we
])
def test_dictionary(heard, typed):
    assert replace.dictionary(heard, WORDS) == typed


@pytest.mark.parametrize("text", [
    "The rohitsingh account.",  # part of a longer word
    "Sherpa is a guide.",  # only part of the phrase
    "",
])
def test_dictionary_leaves_other_words(text):
    assert replace.dictionary(text, WORDS) == text


def test_dictionary_ignores_blank_entries():
    assert replace.dictionary("Hello there.", [["  ", "x"], ["", ""]]) == "Hello there."


SNIPPETS = [["my email", "rohit@example.com"], ["sign off", "Thanks,\nRohit"], ["my address", "12 Park Street\nKolkata"]]


@pytest.mark.parametrize("heard, typed", [
    ("My email.", "rohit@example.com"),
    ("my email", "rohit@example.com"),
    ("Sign off.", "Thanks,\nRohit"),
    ("Send it to my email.", "Send it to rohit@example.com."),
    ("My email is below.", "rohit@example.com is below."),
    ("Ship it to my address, please.", "Ship it to 12 Park Street\nKolkata, please."),
    ("See you soon. Sign-off.", "See you soon. Thanks,\nRohit."),
])
def test_snippets(heard, typed):
    assert replace.snippets(heard, SNIPPETS) == typed


@pytest.mark.parametrize("text", ["My emails are full.", "Check my e mail.", "Nothing here."])
def test_snippets_whole_words_only(text):
    assert replace.snippets(text, SNIPPETS) == text


def test_no_pairs():
    assert replace.snippets("My email.", []) == "My email."
    assert replace.dictionary("rohit", []) == "rohit"

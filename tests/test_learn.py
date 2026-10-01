import pytest

from murmur import learn
from murmur.learn import Fix, corrections, find_span, metaphone, similarity

# What Windows' spell checker says (checked against the real one, see spell.py): case matters,
# a capitalised common word is fine, and it knows many names and tech terms.
_WORDS = {
    "i'm", "using", "for", "this", "thanks", "push", "it", "to", "tonight", "send", "the", "file",
    "we", "deploy", "on", "now", "train", "with", "pie", "torch", "i", "love", "wisper", "flow",
    "ask", "about", "buy", "an", "call", "a", "p", "model", "ran", "engine", "x", "clawed", "it's",
    "sequel", "query", "that's", "great", "wonderful", "news", "their", "they're", "going", "home",
    "ok", "okay", "let's", "go", "meet", "tomorrow", "at", "office", "can", "do", "instead", "maybe",
    "online", "report", "by", "think", "should", "hello", "how", "are", "you", "team", "not",
    "cannot", "have", "five", "apples", "so", "thought", "sherpa", "onyx", "hub", "get", "cooper",
    "nemo", "tron", "is", "here", "apple", "e", "mail", "email", "in", "and", "dear", "more",
    "text", "typed", "later", "check", "please", "nginx", "rising", "run", "my", "laptop", "has",
    "chip", "fix", "bug", "today", "hi", "there", "use", "u.s", "us", "full", "very", "good", "idea",
}
_NAMES = {"Rohit", "Claude", "GitHub", "JSON", "Jason", "SQL", "Kubernetes", "Tuesday", "Thursday",
          "iPhone", "Priya", "Friday", "OK", "API", "Ryzen", "Python", "Can"}


def is_word(w: str) -> bool:
    if w in _NAMES or w in _WORDS:
        return True
    if w[:1].isupper() and w[1:] == w[1:].lower() and w.lower() in _WORDS:
        return True  # start of a sentence
    return any(c.isdigit() for c in w) and w.isdigit()


def fixes(a, b):
    return [(f.heard, f.write, f.strong) for f in corrections(a, b, is_word)]


# ---- Fixes of misheard words ------------------------------------------------------------------

@pytest.mark.parametrize("pasted, edited, expected", [
    ("I'm using Sherpa Onyx for this.", "I'm using sherpa-onnx for this.", ("Sherpa Onyx", "sherpa-onnx", True)),
    ("Thanks, Rohid.", "Thanks, Rohit.", ("Rohid", "Rohit", True)),
    ("Push it to get hub tonight.", "Push it to GitHub tonight.", ("get hub", "GitHub", True)),
    ("We deploy on cooper netties now.", "We deploy on Kubernetes now.", ("cooper netties", "Kubernetes", True)),
    ("Train it with pie torch.", "Train it with PyTorch.", ("pie torch", "PyTorch", True)),
    ("I love Wisper flow.", "I love Wispr Flow.", ("Wisper flow", "Wispr Flow", True)),
    ("Ask rohit about it.", "Ask Rohit about it.", ("rohit", "Rohit", True)),
    ("Buy an Iphone.", "Buy an iPhone.", ("Iphone", "iPhone", True)),
    ("Call the a p i.", "Call the API.", ("a p i", "API", True)),
    ("The Nemo Tron model.", "The Nemotron model.", ("Nemo Tron", "Nemotron", True)),
    ("We use sherpa onnx here.", "We use sherpa-onnx here.", ("sherpa onnx", "sherpa-onnx", True)),
    ("Ask Murmer to do it.", "Ask Murmur to do it.", ("Murmer", "Murmur", True)),
    ("Use GPT four for this.", "Use GPT-4 for this.", ("GPT four", "GPT-4", True)),
    # Real words heard: offered only once seen again.
    ("Ask Clawed about it.", "Ask Claude about it.", ("Clawed", "Claude", False)),
    ("Send the Jason file.", "Send the JSON file.", ("Jason", "JSON", False)),
    ("Check the sequel query.", "Check the SQL query.", ("sequel", "SQL", False)),
    ("I ran engine x today.", "I ran nginx today.", ("engine x", "nginx", False)),
    ("My laptop has a Rising chip.", "My laptop has a Ryzen chip.", ("Rising", "Ryzen", False)),
    ("Buy an apple today.", "Buy an Apple today.", ("apple", "Apple", False)),
    ("It's on Tuesday.", "It's on Thursday.", ("Tuesday", "Thursday", False)),
])
def test_fix(pasted, edited, expected):
    assert fixes(pasted, edited) == [expected]


def test_two_fixes_in_one_dictation():
    assert fixes("Ask Rohid to push it to get hub.", "Ask Rohit to push it to GitHub.") == [
        ("Rohid", "Rohit", True), ("get hub", "GitHub", True)]


def test_fix_next_to_added_words():
    # Fixed a name and added a few words at the end.
    assert fixes("Thanks, Rohid.", "Thanks, Rohit. See you tomorrow.") == [("Rohid", "Rohit", True)]


# ---- Edits that aren't misheard words ---------------------------------------------------------

@pytest.mark.parametrize("pasted, edited", [
    ("That's great news.", "That's wonderful news."),  # a different word
    ("Their going home.", "They're going home."),  # grammar
    ("I think so.", "I thought so."),
    ("OK, let's go.", "Okay, let's go."),  # style, though it sounds the same: OK is a word
    ("Let's meet tomorrow at the office.", "Can we do Friday instead, maybe online?"),  # rewrite
    ("Send the report.", "Send the report to Priya by Friday."),  # additions
    ("I think we should go.", "We should go."),  # deletions
    ("Hello, how are you.", "Hello, how are you?"),  # punctuation
    ("Meet the Team.", "Meet the team."),  # lowercasing
    ("We can not go.", "We cannot go."),  # joined, but not a term
    ("Send an e mail.", "Send an email."),
    ("I have 5 apples.", "I have five apples."),  # numbers
    ("Meet at 3.30pm today.", "Meet at 3:30 pm today."),  # number formatting
    ("Hello there.", "Hello there."),  # unchanged
    ("hello there.", "Hello there."),  # capital at the start of the dictation
    ("Fix the bug. it is good.", "Fix the bug. It is good."),  # ... or of a sentence
    ("Ask Rohid to send Jason the full report via get hub today please.",
     "Ask Rohit to mail Priya a short summary on GitHub tomorrow instead."),  # too much changed
])
def test_not_a_fix(pasted, edited):
    assert fixes(pasted, edited) == []


def test_long_replacements_are_rewrites():
    assert fixes("Use the very good idea here.", "Use something entirely unlike that here.") == []


def test_too_many_fixes_is_an_editing_pass():
    pasted = "Ask Rohid to push to get hub then Murmer said Nemo Tron is here."
    edited = "Ask Rohit to push to GitHub then Murmur said Nemotron is here."
    assert len(corrections(pasted, edited, is_word)) == 0
    assert learn.MAX_FIXES == 3


# ---- Similarity -------------------------------------------------------------------------------

@pytest.mark.parametrize("word, key", [
    ("Thursday", "0RST"), ("Rohid", "RHT"), ("Rohit", "RHT"), ("knight", "NT"),
    ("phone", "FN"), ("sequel", "SKL"), ("SQL", "SKL"), ("nginx", "NJNKS"), ("Kubernetes", "KBRNTS"),
])
def test_metaphone(word, key):
    assert metaphone(word) == key


def test_similarity():
    assert similarity("cooper netties", "Kubernetes") >= learn.MIN_SIMILAR
    assert similarity("sequel", "SQL") >= learn.MIN_SIMILAR
    assert similarity("great", "wonderful") < learn.MIN_SIMILAR
    assert similarity("meeting", "call") < learn.MIN_SIMILAR


# ---- Finding the pasted text again ------------------------------------------------------------

def test_find_unchanged():
    assert find_span(" I'm using Sherpa Onyx.", "Dear team,", "\nThanks",
                     "Dear team, I'm using Sherpa Onyx.\nThanks") == "I'm using Sherpa Onyx."


def test_find_edited():
    assert find_span(" I'm using Sherpa Onyx.", "Dear team,", "\nThanks",
                     "Dear team, I'm using sherpa-onnx.\nThanks") == "I'm using sherpa-onnx."


def test_find_with_text_typed_after():
    # Pasted at the end of the field, then the user fixed a word and kept typing.
    assert find_span("Thanks, Rohid.", "Hi there. ", "",
                     "Hi there. Thanks, Rohit. See you tomorrow.") == "Thanks, Rohit."


def test_find_with_text_typed_before():
    assert find_span("Thanks, Rohid.", "", "", "Oh and thanks, Rohit.") == "thanks, Rohit."


def test_find_first_word_fixed():
    assert find_span("Rohid, can you check?", "Hi ", " Bye", "Hi Rohit, can you check? Bye") == "Rohit, can you check?"


def test_find_among_repeats():
    # The same sentence elsewhere in the document: the anchors pick the pasted one.
    now = ("I'm using Sherpa Onyx. " * 3 + "Some other paragraph here.\nDear team, I'm using sherpa-onnx."
           "\nThanks, Priya")
    assert find_span(" I'm using Sherpa Onyx.", "here.\nDear team,", "\nThanks, Priya", now) == "I'm using sherpa-onnx."


def test_find_cut_context_words():
    # The reads cut words in half at their limits; those halves are ignored.
    assert find_span(" Thanks, Rohid.", "ear team,", "\nThan", "Dear team, Thanks, Rohit.\nThanks") == "Thanks, Rohit."


def test_find_gone():
    assert find_span("Thanks, Rohid, for checking the report.", "Hi. ", "",
                     "Hi. Something else entirely now.") is None


def test_find_then_correct():
    span = find_span(" Push it to get hub tonight.", "Done.", "", "Done. Push it to GitHub tonight. Cheers")
    assert span == "Push it to GitHub tonight."
    assert fixes("Push it to get hub tonight.", span) == [("get hub", "GitHub", True)]


# ---- With Windows' own spell checker ----------------------------------------------------------

def test_real_spell_checker():
    spell = pytest.importorskip("murmur.spell")
    try:
        s = spell.Speller()
    except OSError:
        pytest.skip("no English spell checker")
    got = lambda a, b: [(f.heard, f.write, f.strong) for f in corrections(a, b, s.is_word)]
    assert got("I'm using Sherpa Onyx for this.", "I'm using sherpa-onnx for this.") == [
        ("Sherpa Onyx", "sherpa-onnx", True)]
    assert got("Thanks, Rohid.", "Thanks, Rohit.") == [("Rohid", "Rohit", True)]
    assert got("Push it to get hub tonight.", "Push it to GitHub tonight.") == [("get hub", "GitHub", True)]
    assert got("That's great news.", "That's wonderful news.") == []
    assert got("Their going home.", "They're going home.") == []


def test_leading_space_and_line_breaks():
    # Pasted after a space, with a "new line" command in it.
    assert fixes(" Thanks, Rohid.\nSee you.", "Thanks, Rohit.\nSee you.") == [("Rohid", "Rohit", True)]
    span = find_span(" Thanks, Rohid.\nSee you.", "Done.", "", "Done. Thanks, Rohit.\nSee you.")
    assert span == "Thanks, Rohit.\nSee you."


def test_read_mid_word():
    # Caught while retyping: this looks like a fix too, which is why the app only offers fixes
    # that are still there in the next read (or the last one).
    assert fixes("Thanks, Rohid.", "Thanks, Rohi.") == [("Rohid", "Rohi", True)]
    assert fixes("Thanks, Rohid.", "Thanks, R.") == []


def test_all_deleted():
    assert find_span("Thanks, Rohid.", "Hi. ", " Bye.", "Hi. Bye.") in ("", None)
    assert fixes("Thanks, Rohid.", "") == []


# ---- Learning a fix ---------------------------------------------------------------------------

def fresh(**options):
    return {"dictionary": [], "vocabulary": [], "learned": {"seen": {}, "rejected": []}, **options}


def test_a_non_word_fix_goes_in_the_dictionary_at_once():
    s = fresh(dictionary=[["sherpa onnx", "sherpa-onnx"]])
    option, value, undo = learn.learning(s, Fix("Rohid", "Rohit", True, 0.9))
    assert option == "dictionary"
    assert value == [["sherpa onnx", "sherpa-onnx"], ["Rohid", "Rohit"]]
    assert undo(value) == [["sherpa onnx", "sherpa-onnx"]]


def test_a_new_fix_replaces_the_entry_for_the_same_words():
    s = fresh(dictionary=[["rohid", "Rohith"]])
    option, value, undo = learn.learning(s, Fix("Rohid", "Rohit", True, 0.9))
    assert value == [["Rohid", "Rohit"]]
    assert undo(value) == [["rohid", "Rohith"]]  # undoing brings the old one back


def test_a_fix_already_in_the_dictionary_changes_nothing():
    s = fresh(dictionary=[["Rohid", "Rohit"]])
    assert learn.learning(s, Fix("Rohid", "Rohit", True, 0.9)) is None


def test_a_real_word_fix_goes_in_the_vocabulary_the_second_time():
    s = fresh(vocabulary=["Kubernetes"])
    fix = Fix("Jason", "JSON", False, 0.8)
    assert learn.learning(s, fix) is None
    option, value, undo = learn.learning(s, fix)
    assert (option, value) == ("vocabulary", ["Kubernetes", "JSON"])
    assert undo(value) == ["Kubernetes"]


def test_a_word_already_in_the_vocabulary_isnt_added_again():
    s = fresh(vocabulary=["json"])
    fix = Fix("Jason", "JSON", False, 0.8)
    learn.learning(s, fix)
    assert learn.learning(s, fix) is None


def test_an_undone_fix_is_never_learned_again():
    s = fresh()
    fix = Fix("Rohid", "Rohit", True, 0.9)
    learn.reject(s, fix)
    assert learn.learning(s, fix) is None
    assert learn.learning(s, Fix("rohid", "Rohit", True, 0.9)) is None  # however it was cased


def test_full_lists_are_left_alone():
    s = fresh(dictionary=[[f"w{i}", f"W{i}"] for i in range(learn.MAX_ENTRIES)])
    assert learn.learning(s, Fix("Rohid", "Rohit", True, 0.9)) is None


def test_seen_once_fixes_are_forgotten_oldest_first():
    s = fresh()
    s["learned"]["seen"] = {f"w{i} -> W{i}": 1 for i in range(learn.MAX_REMEMBERED)}
    learn.learning(s, Fix("Jason", "JSON", False, 0.8))
    assert len(s["learned"]["seen"]) == learn.MAX_REMEMBERED
    assert "w0 -> W0" not in s["learned"]["seen"] and "jason -> JSON" in s["learned"]["seen"]

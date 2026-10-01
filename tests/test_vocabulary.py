import pytest

from murmur import pipeline, settings, vocabulary
from murmur.settings import DEFAULTS


def tokens(text: str) -> list[tuple[str, float]]:
    """Text as the model gives it: one piece per word, each starting with a space."""
    return [(" " + word, i * 0.3) for i, word in enumerate(text.split())]


def text(toks) -> str:
    return "".join(piece for piece, _ in toks).strip()


VOCAB = vocabulary.Vocabulary(["Kubernetes", "Vercel", "Claude", "Wispr Flow", "Anirudh", "QWebEngine"])


# Cases from the clips the design was tested on (see vocabulary.py).
@pytest.mark.parametrize("plain, steered, merged", [
    # A term in place of what sounds like it: taken.
    ("We deploy on Cuba or nets today.", "We deploy on Kubernetes today.", "We deploy on Kubernetes today."),
    ("Check the Versal logs.", "Check the Vercel logs.", "Check the Vercel logs."),
    ("Send it to Unirud and Priyanka.", "Send it to Anirudh and Priyanka.", "Send it to Anirudh and Priyanka."),
    ("The Qweb Engine view.", "The QWebEngine view.", "The QWebEngine view."),
    # A term pushed into words that don't sound like it: not taken.
    ("My colleague lives here.", "My Claude lives here.", "My colleague lives here."),
    ("She parked the car near the market.", "She parked the Claude Market.", "She parked the car near the market."),
    # Changes without a term stay as first heard, even next to one.
    ("Whisper Flow uses a hotkey.", "Wisp Airflow uses a hotkey.", "Whisper Flow uses a hotkey."),
    ("Delayed by two hours.", "Delayed by 2 hours.", "Delayed by two hours."),
    # A term out of nowhere: not taken.
    ("Ship it.", "Ship it Kubernetes.", "Ship it."),
])
def test_merge(plain, steered, merged):
    assert text(VOCAB.merge(tokens(plain), tokens(steered))) == merged


def test_merge_keeps_timestamps():
    merged = VOCAB.merge(tokens("on Cuba or nets now"), tokens("on Kubernetes now"))
    assert merged == [(" on", 0.0), (" Kubernetes", 0.3), (" now", 1.2)]  # unchanged words: as first heard


def test_merge_keeps_word_pieces_together():
    plain = [(" Check", 0.0), (" the", 0.2), (" Ver", 0.4), ("sal", 0.5), (" logs", 0.7)]
    steered = [(" Check", 0.0), (" the", 0.2), (" Ver", 0.4), ("cel", 0.5), (" logs", 0.7)]
    assert VOCAB.merge(plain, steered) == steered


@pytest.mark.parametrize("a, b", [("Versal", "Vercel"), ("Cuba or nets", "Kubernetes"), ("PiSide", "PySide"),
                                  ("Sherpa Onyx", "sherpa-onnx"), ("Anirudd", "Anirudh")])
def test_sounds_alike(a, b):
    assert vocabulary.sounds_alike(a, b) >= vocabulary.ALIKE


@pytest.mark.parametrize("a, b", [("colleague", "Claude"), ("car near the", "Claude the"), ("ready", "Rohit")])
def test_sounds_different(a, b):
    assert vocabulary.sounds_alike(a, b) < vocabulary.ALIKE


def test_variants():
    assert vocabulary.variants("sherpa-onnx") == ["sherpa-onnx", "sherpa onnx", "Sherpa onnx", "Sherpa Onnx"]
    assert vocabulary.variants("Kubernetes") == ["Kubernetes"]
    # "/" and ":" mean something in sherpa-onnx's hotword syntax.
    assert vocabulary.variants("a/b:c") == ["a b c", "A b c", "A B C"]


def test_terms_come_from_vocabulary_then_dictionary():
    s = {"vocabulary": ["Kubernetes", "  Wispr   Flow "], "dictionary": [["sherpa onnx", "sherpa-onnx"]]}
    assert vocabulary.terms(s) == ["Kubernetes", "Wispr Flow", "sherpa-onnx"]


def test_terms_skip_repeats_snippets_and_tiny_words():
    s = {"vocabulary": ["Rohit", "rohit", "C++", "ok"], "dictionary": [["rohit", "Rohit"], ["sig", "Best,\nRohit"]]}
    assert vocabulary.terms(s) == ["Rohit"]


def test_no_terms_is_falsy():
    assert not vocabulary.Vocabulary([])
    assert vocabulary.Vocabulary([]).hotwords == ""


def test_pipeline_writes_terms_exactly():
    s = {**DEFAULTS, "vocabulary": ["sherpa-onnx", "Wispr Flow"]}
    assert pipeline.process("I use Sherpa onnx and wispr flow.", s) == "I use sherpa-onnx and Wispr Flow."


def test_pipeline_dictionary_wins_over_vocabulary():
    s = {**DEFAULTS, "vocabulary": ["Gitlab"], "dictionary": [["gitlab", "GitLab"]]}
    assert pipeline.process("Push to gitlab.", s) == "Push to GitLab."


def test_settings_validation():
    assert settings.valid("vocabulary", ["Kubernetes", "Wispr Flow"])
    assert settings.valid("vocabulary", [])
    assert not settings.valid("vocabulary", [""])
    assert not settings.valid("vocabulary", ["x" * 101])
    assert not settings.valid("vocabulary", "Kubernetes")

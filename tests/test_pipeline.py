import pytest

from murmur import cleanup, pipeline, settings

DEFAULTS = settings.DEFAULTS


@pytest.mark.parametrize("spoken", [
    "Uh, it's twenty dollars.",
    "Um, so I think, uh, we should go.",
    "Send it by 3.30pm for 500 rupees.",
    "It was twenty twenty five.",
])
def test_defaults_are_cleanup_tidy(spoken):
    assert pipeline.process(spoken, DEFAULTS) == cleanup.tidy(spoken)


def test_fillers_can_stay():
    assert pipeline.process("Um, it's twenty dollars.", {**DEFAULTS, "remove_fillers": False}) == "Um, it's $20."


def test_numbers_can_stay_words():
    s = {**DEFAULTS, "digits": False}
    assert pipeline.process("Uh, it's twenty dollars.", s) == "It's twenty dollars."
    # Digits the model wrote itself are still tidied.
    assert pipeline.process("Send it by 3.30pm for 500 rupees.", s) == "Send it by 3:30 PM for ₹500."


def test_dictionary_after_cleanup():
    s = {**DEFAULTS, "dictionary": [["rohit", "Rohit"], ["sherpa onnx", "sherpa-onnx"]]}
    assert pipeline.process("Um, ask rohit about sherpa onnx.", s) == "Ask Rohit about sherpa-onnx."


def test_settings_validation():
    assert settings.valid("dictionary", [["a b", "c"]])
    assert not settings.valid("dictionary", [["a b", ""]])
    assert not settings.valid("dictionary", [["a", "b", "c"]])
    assert settings.valid("digits", False)
    assert not settings.valid("digits", "no")
    assert not settings.valid("hotkey", ["f9"])  # changed through its own slot

"""Capitals the speech model gets wrong.

- `continue_sentence`: the model writes every dictation as if it starts a sentence. Said into
  the middle of one ("I think |"), the first word shouldn't keep its capital: "I think we
  should ship it", not "I think We should ship it". What's before the caret is read anyway, for
  the space (spacing.py); it also says whether a sentence is being continued. Only common words
  lose the capital: names, "I", acronyms, the user's own words and anything not on the list keep
  theirs (a miss at worst, never a wrong change). So does the first word of a name in capitals
  ("New York", "The Beatles").
- `capital_i`: "i", "i'm", "i'll" on their own are "I". The model wrote them in lowercase a few
  times in long dictations. "for i in" (code) is left alone.
"""
import re

# After these (and spaces), the text carries on the sentence. Not after . ! ? : quotes or
# brackets, where either can be right.
_CONTINUES = ",;—–"
# The first word, and the capital starting the next one if any (not "I": "So I think").
_FIRST = re.compile(r"([A-Z][a-z]*(?:'[a-z]+)?)(?![\w'])(\s+(?!I\b)[A-Z])?")

# Words that start a clause carried on from what's before ("and", "we", "the"). Not names that
# are also words (May, Will, Bill), and not "I".
COMMON = set("""
a about above actually after again against all almost also although always am an and another
any anyone anything anyway are around as at away back basically be because been before being
below besides between both but by can can't cannot could couldn't did didn't do does doesn't
doing don't done down during each either else enough especially even ever every everyone
everything except few first for from further get gets getting give go goes going gonna got had
hadn't has hasn't have haven't having he he'd he'll he's her here here's hers herself him
himself his honestly how however if in including instead into is isn't it it'd it'll it's its
itself just keep kind know last later least less let let's like likely look made make makes
many maybe me mean means might more most mostly much must my myself need needs never next no
nobody none nor not nothing now of off often oh okay on once one ones only onto or other others
otherwise our ours ourselves out over own perhaps please plus probably put quite rather really
right said same say says see seems she she'd she'll she's should shouldn't show since so some
someone something sometimes somewhere soon still such sure take than thank thanks that that'll
that's the their theirs them themselves then there there's these they they'd they'll they're
they've thing things think this those though through thus to together too toward towards try
under unless until up upon us use used using usually very via want wants was wasn't way we we'd
we'll we're we've well were weren't what what's whatever when whenever where whereas wherever
whether which while who who's whoever whole whom whose why will with within without won't would
wouldn't yeah yes yet you you'd you'll you're you've your yours yourself yourselves
""".split())


def continues_sentence(before: str | None) -> bool:
    """Whether text put after `before` (the characters before the caret; "" at the start of a
    field, None if unknown) carries on a sentence."""
    if not before:
        return False
    last = before.rstrip(" \t\u00a0")[-1:]
    return bool(last) and (last.isalnum() or last in _CONTINUES)


def continue_sentence(text: str, before: str | None, keep=()) -> str:
    """`text` with its first word in lowercase if it carries on the sentence before the caret.
    `keep`: the user's own words, written as they gave them."""
    if not continues_sentence(before):
        return text
    m = _FIRST.match(text)
    if not m or m.group(2) or m.group(1).lower() not in COMMON:
        return text
    word = m.group(1)
    if any(t.split()[0] == word for t in keep if t.strip()):
        return text
    return word.lower() + text[m.end(1):]


_I = re.compile(r"(?<![\w'.\-/@])i(?='(?:m|ll|ve|d)(?![\w'])|[ \t,;!?]|$)")
_FOR = re.compile(r"\bfor\s+$", re.IGNORECASE)


def capital_i(text: str) -> str:
    if "i" not in text:
        return text
    return _I.sub(lambda m: m.group(0) if _FOR.search(text, 0, m.start()) else "I", text)

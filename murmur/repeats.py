"""Stutters: a small word said twice by accident ("to to", "like, like", "on the. The next"), or
a word started and started again ("ch chatbot", "my l laptop"). The speech model writes them
down as said.

Only words nobody doubles on purpose go: some pronouns, articles, conjunctions, prepositions.
"Very, very", "bye bye", "no no", "that that" ("I know that that's true"), "had had", "is is"
("what it is is") stay. The word kept takes the case of the one dropped: "The the build" is "The
build", "on the. The next day" is "on the next day".

A false start is one or two lowercase letters that aren't a word, before a word starting with
them. Capitals are left alone: "C compiler", "S Sharma" are a letter and a word.
"""
import re

DOUBLED = set("""
a an and because but for from i i'd i'll i'm i've if into it's like of or our she the their them
they to we when with your
""".split())
# Not "it", "you", "this": they end one clause and start the next, and the model often leaves
# out the comma between ("I trust you you can", "I was on it it just broke"). Nor "at" ("look at
# at least"), "in", "on" ("log in in the morning").

# Of those, the ones no sentence or clause ends on. Across a comma or a full stop, the others
# can be said twice on purpose ("So did I. I really did", "Ask them, them and the team"). There
# they go only if the model didn't start a new sentence with the second, or (comma) they're "I"
# or "like", which hardly end a clause and often stutter.
_NEVER_LAST = set("a an and because but for from i'd i'll i'm i've if into it's of or our the their to your".split())
_COMMA = _NEVER_LAST | {"i", "like"}
# Real words (and common abbreviations) of one or two letters, which a false start can't be.
_SHORT_WORDS = set("""
a i ad ah ai am an as at aw ax be by db do dr eh ex go ha he hi hm hr id if in ip is it jr js la
lo ma me mi ml mm mr ms mu my no nu of oh ok on or os ow ox pa pc pi pm re so st ta ti to tv uh
ui um up us ux vs we ya ye yo
""".split())

_DOUBLE = re.compile(r"(?<![\w'])([a-z]+(?:'[a-z]+)?)([,.]?)\s+(?=(\1)(?![\w']))", re.IGNORECASE)
_FALSE_START = re.compile(r"(?<![\w'])([a-z]{1,2})-?\s+(?=\1[a-z])")


def remove(text: str) -> str:
    # From the end, so earlier matches' positions still hold.
    for m in reversed(list(_DOUBLE.finditer(text))):
        dropped, stop, kept = m.groups()
        word = dropped.lower()
        stutter = (not stop or stop == "," and word in _COMMA
                   or stop == "." and (word in _NEVER_LAST or kept[0].islower()))
        if word in DOUBLED and stutter:
            text = text[:m.start()] + dropped[0] + kept[1:] + text[m.end() + len(kept):]
    return _FALSE_START.sub(lambda m: m.group(0) if m.group(1) in _SHORT_WORDS else "", text)

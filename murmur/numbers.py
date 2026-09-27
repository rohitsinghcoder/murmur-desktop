"""Writes spoken numbers the way people type them.

"twenty twenty five" → 2025, "fifty percent" → 50%, "three thirty pm" → 3:30 PM, "twenty five
dollars" → $25. Small numbers on their own stay words ("one thing", "two of them"), and anything
ambiguous is left as spoken. Port of the Android app's Numbers.kt.
"""
import re
from dataclasses import dataclass
from enum import Enum, auto

UNITS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
TEENS = ["ten", "eleven", "twelve", "thirteen", "fourteen",
         "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
TENS = ["twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
SCALES = {"thousand": 1_000, "million": 1_000_000, "billion": 1_000_000_000}
CONNECTORS = {"and", "point", "oh"}

_word = re.compile(r"[A-Za-z']+")
_joiner = re.compile(r"[ \t-]+")
_percent = re.compile(r"^[ -]?(?:percent|per cent)\b", re.IGNORECASE)
_currency = re.compile(r"^ (dollars?|rupees?|euros?)\b", re.IGNORECASE)
_ampm = re.compile(r"^ ?([ap])\.? ?m(?![a-z])(\.)?", re.IGNORECASE)
_keeps_digits = re.compile(r"^ (?:lakhs?|crores?|o'clock)\b", re.IGNORECASE)
_decade_next = re.compile(r"^ (?:\w+ties|hundreds|thousands|millions)\b", re.IGNORECASE)
TIME_CUES = {"at", "by", "around", "till", "until", "from", "after", "before", "about"}


class Kind(Enum):
    NONE = auto()
    UNIT = auto()
    TEEN = auto()
    TENS = auto()
    HUNDRED = auto()
    SCALE = auto()


@dataclass
class Num:
    """One number within a run of number words."""
    value: int
    words: int
    decimals: str = ""
    oh: bool = False
    # The number ended in "million" or "billion": written "5 million", not 5,000,000.
    scale: tuple[str, int] | None = None

    @property
    def digit(self) -> bool:
        return self.words == 1 and not self.decimals and self.value < 10


def _small(w: str) -> int | None:
    if w in UNITS:
        return UNITS.index(w)
    if w in TEENS:
        return TEENS.index(w) + 10
    if w in TENS:
        return 20 + TENS.index(w) * 10
    return None


def _is_start(w: str) -> bool:
    return _small(w) is not None


def _is_number_word(w: str) -> bool:
    return _is_start(w) or w == "hundred" or w in SCALES or w in CONNECTORS


def format(text: str) -> str:
    words = list(_word.finditer(text))
    if not any(_is_start(m.group().lower()) for m in words):
        return text
    out = []
    pos = 0
    i = 0
    while i < len(words):
        first = words[i]
        if first.start() < pos or not _is_start(first.group().lower()):
            i += 1
            continue
        # The run of number words joined only by spaces or hyphens.
        j = i
        while (
            j + 1 < len(words)
            and _joiner.fullmatch(text[words[j].end():words[j + 1].start()])
            and _is_number_word(words[j + 1].group().lower())
        ):
            j += 1
        while j > i and words[j].group().lower() in CONNECTORS:
            j -= 1

        run = [m.group().lower() for m in words[i:j + 1]]
        items, used = _parse(run)
        end = words[i + used - 1].end()
        prev = None
        if i > 0 and not text[words[i - 1].end():first.start()].strip():
            prev = words[i - 1].group().lower()
        written = _write(items, run[0], prev, text[end:])
        if written is not None:
            out.append(text[pos:first.start()])
            out.append(written[0])
            pos = end + written[1]
        i += used
    out.append(text[pos:])
    return "".join(out)


def _parse(w: list[str]) -> tuple[list[Num], int]:
    """Splits a run like "twenty twenty five" into numbers (20, 25).

    Stops early at an "and" or "point" that doesn't belong to a number; returns the numbers
    and words used.
    """
    items: list[Num] = []
    total = cur = count = 0
    last = Kind.NONE
    last_scale = float("inf")
    scale_word = None

    def reset():
        nonlocal total, cur, last, count, last_scale, scale_word
        total = cur = count = 0
        last = Kind.NONE
        last_scale = float("inf")
        scale_word = None

    def close():
        if count > 0:
            v = total + cur
            s = None
            if scale_word is not None:
                size = SCALES[scale_word]
                if v % size == 0 and size >= 1_000_000:
                    s = (scale_word, size)
            items.append(Num(v, count, scale=s))
        reset()

    i = 0
    while i < len(w):
        t = w[i]
        if t == "and":
            nxt = w[i + 1] if i + 1 < len(w) else None
            if last in (Kind.HUNDRED, Kind.SCALE) and nxt is not None and _small(nxt) is not None:
                count += 1
                i += 1
                continue
            break
        if t == "point":
            j = i + 1
            digits = ""
            while j < len(w) and (_small(w[j]) if _small(w[j]) is not None else 10) < 10:
                digits += str(_small(w[j]))
                j += 1
            if count == 0 or not digits:
                break
            items.append(Num(total + cur, count + 1 + len(digits), decimals=digits))
            reset()
            i = j
            continue
        if t == "oh":
            close()
            items.append(Num(0, 1, oh=True))
            i += 1
            continue

        v = _small(t)
        if v is None:
            kind = Kind.HUNDRED if t == "hundred" else Kind.SCALE
        elif v < 10:
            kind = Kind.UNIT
        elif v < 20:
            kind = Kind.TEEN
        else:
            kind = Kind.TENS

        if kind == Kind.UNIT:
            fits = last == Kind.NONE if v == 0 else last in (Kind.NONE, Kind.TENS, Kind.HUNDRED, Kind.SCALE)
        elif kind in (Kind.TEEN, Kind.TENS):
            fits = last in (Kind.NONE, Kind.HUNDRED, Kind.SCALE)
        elif kind == Kind.HUNDRED:
            fits = last in (Kind.UNIT, Kind.TEEN) and 1 <= cur <= 99
        else:
            fits = last != Kind.NONE and cur > 0 and SCALES[t] < last_scale
        if not fits:
            # "hundred" or "thousand" can't start a number: the run ends here.
            if kind in (Kind.HUNDRED, Kind.SCALE):
                break
            close()

        if kind == Kind.HUNDRED:
            cur *= 100
        elif kind == Kind.SCALE:
            s = SCALES[t]
            total += cur * s
            cur = 0
            last_scale = s
            scale_word = t
        else:
            cur += v
        if kind != Kind.SCALE:
            scale_word = None
        last = kind
        count += 1
        i += 1
    close()
    return items, i


def _write(items: list[Num], first_word: str, prev: str | None, rest: str) -> tuple[str, int] | None:
    """The written form of a run and how many characters after it were absorbed, or None to keep the words."""
    if not items:
        return None
    a = items[0]

    # Years: "nineteen ninety nine", "twenty twenty five", "twenty oh five".
    if first_word in ("nineteen", "twenty"):
        if len(items) == 2 and a.words == 1 and not items[1].decimals and not items[1].oh and 10 <= items[1].value <= 99:
            return str(a.value * 100 + items[1].value), 0
        if len(items) == 3 and a.words == 1 and items[1].oh and items[2].digit and items[2].value > 0:
            return str(a.value * 100 + items[2].value), 0
    if len(items) == 2 and a.value == 24 and a.words == 2 and items[1].digit and items[1].value == 7:
        return "24/7", 0

    # Times: "three thirty pm", "at ten fifteen", "seven am".
    meridiem = _ampm.search(rest)
    if a.words == 1 and 1 <= a.value <= 12 and (meridiem or (prev is not None and prev in TIME_CUES)):
        minutes = None
        if len(items) == 2 and not items[1].decimals and not items[1].oh and 10 <= items[1].value <= 59:
            minutes = items[1].value
        elif len(items) == 3 and items[1].oh and items[2].digit and items[2].value > 0:
            minutes = items[2].value
        suffix = None
        if meridiem:
            m = " " + meridiem.group(1).upper() + "M"
            # Keep a sentence-ending period that was part of "p.m.".
            after = rest[meridiem.end():]
            ends_sentence = bool(meridiem.group(2)) and (not after.strip() or after.lstrip()[:1].isupper())
            suffix = (m + "." if ends_sentence else m, len(meridiem.group(0)))
        if minutes is not None:
            return f"{a.value}:{minutes:02d}{suffix[0] if suffix else ''}", suffix[1] if suffix else 0
        if len(items) == 1 and suffix:
            return f"{a.value}{suffix[0]}", suffix[1]

    # Spelled-out digits, like a phone number: "nine eight seven six".
    if len(items) >= 3 and all(it.digit or it.oh for it in items):
        return "".join(str(it.value) for it in items), 0

    # Anything else made of several numbers is ambiguous ("one two", "five ten"): keep it.
    if len(items) != 1:
        return None
    if _decade_next.search(rest):  # "the nineteen sixties"
        return None
    if m := _percent.search(rest):
        return f"{_digits(a)}%", len(m.group(0))
    if m := _currency.search(rest):
        symbol = {"d": "$", "r": "₹"}.get(m.group(1)[0].lower(), "€")
        return f"{symbol}{_digits(a)}", len(m.group(0))
    if a.value >= 10 or a.decimals or _keeps_digits.search(rest):
        return _digits(a), 0
    return None


_digit_time = re.compile(r"\b(\d{1,2})(?:[.:](\d{2}))?\s?([ap])\.?\s?m(\.)?(?![a-z])", re.IGNORECASE)
_digit_money = re.compile(r"\b(\d[\d,]*(?:\.\d+)?)\s(rupees?|dollars?|bucks|euros?)\b", re.IGNORECASE)
_rs = re.compile(r"\b(?:rs\.?|inr)\s?(\d[\d,]*(?:\.\d+)?)\b", re.IGNORECASE)
_digit_percent = re.compile(r"(\d)\s?(?:percent|per cent)\b", re.IGNORECASE)
_SYMBOLS = {"r": "₹", "d": "$", "b": "$", "e": "€"}


def tidy_digits(text: str) -> str:
    """The same conventions for numbers the model already wrote as digits:
    "3.30pm" → 3:30 PM, "500 rupees" / "Rs 500" → ₹500, "50 percent" → 50%."""

    def time_(m: re.Match) -> str:
        hour, minutes = int(m.group(1)), m.group(2)
        if not 1 <= hour <= 12 or (minutes and int(minutes) > 59):
            return m.group(0)
        rest = text[m.end():]
        # Keep a sentence-ending period that was part of "p.m.".
        ends = m.group(4) and (not rest.strip() or rest.lstrip()[:1].isupper())
        return f"{hour}{':' + minutes if minutes else ''} {m.group(3).upper()}M{'.' if ends else ''}"

    text = _digit_time.sub(time_, text)
    text = _digit_money.sub(lambda m: _SYMBOLS[m.group(2)[0].lower()] + m.group(1), text)
    text = _rs.sub(lambda m: "₹" + m.group(1), text)
    return _digit_percent.sub(r"\1%", text)


def _digits(n: Num) -> str:
    if n.scale:
        word, size = n.scale
        return f"{_grouped(n.value // size)} {word}"
    return _grouped(n.value) + ("." + n.decimals if n.decimals else "")


def _grouped(v: int) -> str:
    # No separators under 10,000, so years and "2500" stay as typed.
    return f"{v:,}" if v >= 10_000 else str(v)

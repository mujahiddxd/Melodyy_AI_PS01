"""Deterministic quantity parsing (Appendix C). The LLM only extracts the words; this module decides the numbers.

normalize("half", None, "kilo")  -> 0.5 kg          normalize("pav", None, "kilo") -> 0.25 kg
normalize("ek", None, "packet")  -> 1 packet        normalize(None, None, "darjan") -> 12 pc
normalize("thoda", ...)          -> vague (value None, vague=True): always clarified, never guessed
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

D = Decimal


@dataclass(frozen=True)
class NormQty:
    value: Decimal | None  # in `unit`; None when vague or not given
    unit: str | None  # kg | g | l | ml | packet | pc   (dozen is converted to pc)
    vague: bool = False
    missing: bool = False  # nothing about quantity was said


# ---- number words (Hindi, Marathi, English; Roman + Devanagari) -----------------------------------------
_NUMBER_WORDS: dict[str, int] = {}


def _add(value: int, *words: str) -> None:
    for w in words:
        _NUMBER_WORDS[w] = value


_add(1, "ek", "एक", "one", "ik")
_add(2, "do", "दो", "don", "दोन", "two", "dono")
_add(3, "teen", "तीन", "three", "tin")
_add(4, "char", "chaar", "चार", "four")
_add(5, "paanch", "panch", "pach", "paach", "पाँच", "पांच", "पाच", "five")
_add(6, "chhe", "chhah", "chah", "che", "saha", "छह", "छः", "सहा", "six")
_add(7, "saat", "sat", "सात", "seven")
_add(8, "aath", "ath", "आठ", "eight")
_add(9, "nau", "nav", "नौ", "नऊ", "nine")
_add(10, "das", "daha", "दस", "दहा", "ten")
_add(12, "barah", "baara", "बारह", "twelve")
_add(20, "bees", "vis", "बीस", "वीस", "twenty")

# ---- fractions ------------------------------------------------------------------------------------------
# "multiplicative": "teen pav" = 3 x 0.25. "absolute": "dedh kilo" = 1.5.
_FRAC_MULT = {"pav": D("0.25"), "paav": D("0.25"), "पाव": D("0.25"), "adha": D("0.5"), "aadha": D("0.5"),
              "aadhi": D("0.5"), "adhi": D("0.5"), "आधा": D("0.5"), "आधी": D("0.5"), "half": D("0.5"),
              "ardha": D("0.5"), "अर्धा": D("0.5"), "अर्ध": D("0.5"), "अर्धी": D("0.5"), "quarter": D("0.25")}
_FRAC_ABS = {"dedh": D("1.5"), "डेढ़": D("1.5"), "डेढ": D("1.5"), "didh": D("1.5"), "दीड": D("1.5"),
             "dhai": D("2.5"), "dhaai": D("2.5"), "ढाई": D("2.5"), "adich": D("2.5"), "अडीच": D("2.5")}
# modifiers applied to the following number: "sawa do" = 2.25, "paune do" = 1.75, "sade teen" = 3.5
_MODIFIERS = {"sawa": D("0.25"), "sava": D("0.25"), "सवा": D("0.25"),
              "paune": D("-0.25"), "paun": D("-0.25"), "पौने": D("-0.25"), "पाऊण": D("-0.25"),
              "sade": D("0.5"), "sadhe": D("0.5"), "साढ़े": D("0.5"), "साडे": D("0.5")}
_MODIFIER_ALONE = {"sawa": D("1.25"), "sava": D("1.25"), "सवा": D("1.25"),
                   "paune": D("0.75"), "paun": D("0.75"), "पौने": D("0.75"), "पाऊण": D("0.75")}
_GLYPHS = {"½": D("0.5"), "¼": D("0.25"), "¾": D("0.75")}

# ---- units ----------------------------------------------------------------------------------------------
_UNITS: dict[str, tuple[str, int]] = {}


def _unit(canon: str, mult: int, *words: str) -> None:
    for w in words:
        _UNITS[w] = (canon, mult)


_unit("kg", 1, "kilo", "kilos", "kg", "kgs", "kilogram", "kilograms", "किलो", "किग्रा", "केजी", "किलोग्राम", "कि.ग्रा")
_unit("g", 1, "gram", "grams", "gm", "gms", "g", "gr", "ग्राम", "ग्रॅम", "ग्रम")
_unit("l", 1, "litre", "liter", "litres", "liters", "ltr", "ltrs", "l", "lt", "lit", "लीटर", "लिटर", "ली")
_unit("ml", 1, "ml", "mls", "millilitre", "milliliter", "मिली", "मि.ली", "एमएल")
_unit("packet", 1, "packet", "packets", "pkt", "pkts", "paket", "pack", "पैकेट", "पॅकेट", "पाकीट", "पाकिट", "पुडा", "पुड़ा", "पुडे")
_unit("pc", 12, "dozen", "darjan", "darjen", "dozan", "डझन", "दर्जन")
_unit("pc", 1, "piece", "pieces", "pc", "pcs", "nag", "नग", "पीस")

VAGUE_WORDS = {"thoda", "thodi", "thode", "thora", "kuch", "jitna", "jitni", "zara", "थोडा", "थोडं", "थोडे", "थोड़ा",
               "थोड़ी", "थोडी", "कुछ", "जितना", "जितनी", "ज़रा", "जरा"}

_SPLIT = re.compile(r"[\s,;:!?()\[\]{}\"']+")
_NUM_UNIT = re.compile(r"^(\d+(?:[.,]\d+)?)([^\d.,/].*)$")
_DEVA_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


def _tokens(text: str | None) -> list[str]:
    if not text:
        return []
    out: list[str] = []
    for raw in _SPLIT.split(text.translate(_DEVA_DIGITS).lower()):
        t = raw.strip(".")
        if not t:
            continue
        m = _NUM_UNIT.match(t)  # "250gm" -> "250", "gm"
        if m and m.group(2).strip("."):
            out += [m.group(1), m.group(2).strip(".")]
        else:
            out.append(t)
    return out


def _as_number(tok: str) -> Decimal | None:
    if tok in _GLYPHS:
        return _GLYPHS[tok]
    if re.fullmatch(r"\d+/\d+", tok):
        a, b = tok.split("/")
        return D(a) / D(b) if int(b) else None
    if re.fullmatch(r"\d+(?:[.,]\d+)?", tok):
        return D(tok.replace(",", "."))
    if tok in _NUMBER_WORDS:
        return D(_NUMBER_WORDS[tok])
    return None


def _quantize(v: Decimal) -> Decimal:
    return v.quantize(D("0.001")).normalize() if v != v.to_integral() else v.to_integral()


def normalize(
    quantity_text: str | None = None,
    quantity_value: float | int | str | None = None,
    unit_text: str | None = None,
    raw_text: str | None = None,
) -> NormQty:
    """Turn the words the parser extracted into (value, canonical unit). Unknown tokens are ignored."""
    toks = _tokens(quantity_text) + _tokens(unit_text)
    nums: list[Decimal] = []
    unit: str | None = None
    mult = 1
    vague = False
    frac_mult: Decimal | None = None
    frac_abs: Decimal | None = None
    modifier: str | None = None

    for t in toks:
        if t in VAGUE_WORDS:
            vague = True
        elif t in _UNITS:
            unit, mult = _UNITS[t]
        elif t in _MODIFIERS:
            modifier = t
        elif t in _FRAC_ABS:
            frac_abs = _FRAC_ABS[t]
        elif t in _FRAC_MULT:
            frac_mult = _FRAC_MULT[t]
        else:
            n = _as_number(t)
            if n is not None:
                nums.append(n)

    value: Decimal | None = None
    if frac_abs is not None:
        value = frac_abs
    elif frac_mult is not None:
        value = (nums[0] if nums else D(1)) * frac_mult
    elif nums:
        value = nums[0]
        if modifier:
            value += _MODIFIERS[modifier]
    elif modifier in _MODIFIER_ALONE:
        value = _MODIFIER_ALONE[modifier]
    elif quantity_value is not None:
        try:
            value = D(str(quantity_value))
        except Exception:
            value = None

    if vague and not nums and frac_abs is None and frac_mult is None:
        return NormQty(None, unit, vague=True)
    if value is None:
        if unit is not None and mult == 12:  # bare "dozen" / "darjan"
            return NormQty(D(12), "pc")
        return NormQty(None, unit, missing=True)
    if value <= 0:
        return NormQty(None, unit, missing=True)
    return NormQty(_quantize(value * mult), unit)


def extract_quantity(text: str) -> NormQty | None:
    """For free-text answers ("sunflower wala 1 litre"). Only trusts a digit, a unit or a fraction word, because
    plain number words are too ambiguous in Hinglish ("tel do" = "give oil")."""
    q = normalize(text)
    if q.value is None:
        return None
    toks = _tokens(text)
    has_digit = any(re.fullmatch(r"[\d./,]+", t) or t in _GLYPHS for t in toks)
    has_frac = any(t in _FRAC_MULT or t in _FRAC_ABS or t in _MODIFIERS for t in toks)
    return q if (q.unit is not None or has_digit or has_frac) else None


# ---- dimensions (used by inventory + matcher) -----------------------------------------------------------
def to_base(value: Decimal, unit: str | None) -> tuple[str, Decimal]:
    """(dimension, amount in the dimension's smallest unit). Dimensions: mass(g) volume(ml) count(pc) packet none."""
    if unit == "kg":
        return "mass", value * 1000
    if unit == "g":
        return "mass", value
    if unit == "l":
        return "volume", value * 1000
    if unit == "ml":
        return "volume", value
    if unit == "pc":
        return "count", value
    if unit == "dozen":
        return "count", value * 12
    if unit == "packet":
        return "packet", value
    return "none", value


def canonical_qty(q: NormQty) -> Decimal | None:
    """The quantity in kg / l / pc / packet (what order_items.normalized_qty stores)."""
    if q.value is None:
        return None
    dim, base = to_base(q.value, q.unit)
    if dim in ("mass", "volume"):
        return base / 1000
    return base

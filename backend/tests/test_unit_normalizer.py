"""Appendix C: Hindi / Marathi / English number words, fractions and units, Roman and Devanagari."""
from decimal import Decimal

import pytest

from app.services.unit_normalizer import canonical_qty, extract_quantity, normalize


def q(*args, **kw):
    r = normalize(*args, **kw)
    return (None if r.value is None else Decimal(str(r.value)), r.unit, r.vague)


@pytest.mark.parametrize(
    "qty_text, unit_text, expected",
    [
        ("half", "kilo", (Decimal("0.5"), "kg", False)),
        ("pav", "kilo", (Decimal("0.25"), "kg", False)),
        ("paav", "kg", (Decimal("0.25"), "kg", False)),
        ("adha", "kilo", (Decimal("0.5"), "kg", False)),
        ("aadha", "kilo", (Decimal("0.5"), "kg", False)),
        ("sawa", "kilo", (Decimal("1.25"), "kg", False)),
        ("dedh", "kilo", (Decimal("1.5"), "kg", False)),
        ("dhai", "kilo", (Decimal("2.5"), "kg", False)),
        ("paune", "kilo", (Decimal("0.75"), "kg", False)),
        ("paune do", "kilo", (Decimal("1.75"), "kg", False)),
        ("sawa do", "kilo", (Decimal("2.25"), "kg", False)),
        ("sade teen", "kilo", (Decimal("3.5"), "kg", False)),
        ("teen pav", "kilo", (Decimal("0.75"), "kg", False)),
        ("ek", "packet", (Decimal("1"), "packet", False)),
        ("3", "packet", (Decimal("3"), "packet", False)),
        ("ek", "darjan", (Decimal("12"), "pc", False)),
        (None, "dozen", (Decimal("12"), "pc", False)),
        ("do", "dozen", (Decimal("24"), "pc", False)),
        ("2", "kilo", (Decimal("2"), "kg", False)),
        ("250", "gm", (Decimal("250"), "g", False)),
        ("250gm", None, (Decimal("250"), "g", False)),
        ("1.5", "ltr", (Decimal("1.5"), "l", False)),
        ("1.5ltr", None, (Decimal("1.5"), "l", False)),
        ("500", "ml", (Decimal("500"), "ml", False)),
        ("5", "pc", (Decimal("5"), "pc", False)),
        # Devanagari Hindi
        ("दो", "किलो", (Decimal("2"), "kg", False)),
        ("एक", "पैकेट", (Decimal("1"), "packet", False)),
        ("आधा", "किलो", (Decimal("0.5"), "kg", False)),
        ("डेढ़", "किलो", (Decimal("1.5"), "kg", False)),
        ("ढाई", "किलो", (Decimal("2.5"), "kg", False)),
        ("सवा", "किलो", (Decimal("1.25"), "kg", False)),
        ("पाव", "किलो", (Decimal("0.25"), "kg", False)),
        ("२", "किलो", (Decimal("2"), "kg", False)),
        # Marathi
        ("दोन", "किलो", (Decimal("2"), "kg", False)),
        ("अर्धा", "किलो", (Decimal("0.5"), "kg", False)),
        ("don", "kilo", (Decimal("2"), "kg", False)),
        ("ardha", "kilo", (Decimal("0.5"), "kg", False)),
        ("didh", "kilo", (Decimal("1.5"), "kg", False)),
        ("adich", "kilo", (Decimal("2.5"), "kg", False)),
        ("एक", "डझन", (Decimal("12"), "pc", False)),
        ("एक", "पुडा", (Decimal("1"), "packet", False)),
        # English
        ("two", "kg", (Decimal("2"), "kg", False)),
        ("half", "litre", (Decimal("0.5"), "l", False)),
    ],
)
def test_quantities(qty_text, unit_text, expected):
    assert q(qty_text, None, unit_text) == expected


@pytest.mark.parametrize("word", ["thoda", "thodi", "kuch", "jitna", "थोडा", "थोडं", "कुछ"])
def test_vague_words_give_null_quantity(word):
    r = normalize(word, None, None)
    assert r.value is None and r.vague is True


def test_thoda_zyada_is_vague():
    assert normalize("thoda zyada").vague


def test_vague_with_unit_keeps_unit_but_no_value():
    r = normalize("thoda", None, "kilo")
    assert r.value is None and r.vague and r.unit == "kg"


def test_missing_quantity():
    r = normalize(None, None, None)
    assert r.value is None and not r.vague and r.missing


def test_falls_back_to_numeric_value_from_the_parser():
    assert q(None, 2, "kilo") == (Decimal("2"), "kg", False)
    assert q("", 0.5, "l") == (Decimal("0.5"), "l", False)


def test_zero_or_negative_is_not_a_quantity():
    assert normalize("0", None, "kg").value is None


def test_canonical_qty_converts_to_kg_l():
    assert canonical_qty(normalize("250", None, "g")) == Decimal("0.25")
    assert canonical_qty(normalize("500", None, "ml")) == Decimal("0.5")
    assert canonical_qty(normalize("do", None, "dozen")) == Decimal("24")


def test_extract_quantity_ignores_plain_number_words():
    assert extract_quantity("tel do") is None  # "give oil", not 2
    assert extract_quantity("nahi chahiye") is None
    r = extract_quantity("sunflower wala 1 litre")
    assert r is not None and r.value == 1 and r.unit == "l"
    r = extract_quantity("aadha kilo")
    assert r is not None and r.value == Decimal("0.5") and r.unit == "kg"

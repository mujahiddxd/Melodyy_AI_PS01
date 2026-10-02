"""Canned LLM outputs for the 6 demo messages (LLM_MOCK=true). A safety net if the internet fails during judging.

Keyed by task, then by the lowercased customer message. Only the LLM's part is canned: matching, stock, prices and
chips still come from the database.
"""

DEMO_MESSAGES = {
    1: "bhaiya 2 kilo atta, ek Amul butter aur sugar half kilo, tel bhi chahiye",
    2: "दो किलो चावल और एक पैकेट नमक भेज दो",
    3: "दोन किलो तांदूळ आणि अर्धा किलो साखर पाठवा",
    4: "amool butter aur parle g 3 packet",
    5: "asdkj qwe zz",
    6: "oats aur thoda cheeni",
}


def _item(text: str, raw: str, name: str, *, brand=None, value=None, qty=None, unit=None, vague=False) -> dict:
    start = text.index(raw)
    return {
        "raw_text": raw, "name_guess": name, "brand_guess": brand, "quantity_value": value, "quantity_text": qty,
        "unit_text": unit, "is_vague": vague, "refers_to_history": False, "target_item_ref": None,
        "source_span": [start, start + len(raw)],
    }


def _parsed(language, script, items, intent="new_order", notes=None) -> dict:
    return {"language": language, "script": script, "intent": intent, "items": items,
            "delivery_time_text": None, "notes": notes}


def _intake(language, script, category) -> dict:
    return {"language": language, "script": script, "category": category}


M = DEMO_MESSAGES

PARSER = {
    M[1].lower(): _parsed("hinglish", "latin", [
        _item(M[1], "2 kilo atta", "atta", value=2, qty="2", unit="kilo"),
        _item(M[1], "ek Amul butter", "butter", brand="Amul", value=1, qty="ek"),
        _item(M[1], "sugar half kilo", "sugar", qty="half", unit="kilo"),
        _item(M[1], "tel", "tel"),
    ], notes="oil type not said"),
    M[2].lower(): _parsed("hindi", "devanagari", [
        _item(M[2], "दो किलो चावल", "चावल", qty="दो", unit="किलो"),
        _item(M[2], "एक पैकेट नमक", "नमक", qty="एक", unit="पैकेट"),
    ]),
    M[3].lower(): _parsed("marathi", "devanagari", [
        _item(M[3], "दोन किलो तांदूळ", "तांदूळ", qty="दोन", unit="किलो"),
        _item(M[3], "अर्धा किलो साखर", "साखर", qty="अर्धा", unit="किलो"),
    ]),
    M[4].lower(): _parsed("hinglish", "latin", [
        _item(M[4], "amool butter", "butter", brand="amool"),
        _item(M[4], "parle g 3 packet", "parle g", value=3, qty="3", unit="packet"),
    ]),
    M[6].lower(): _parsed("hinglish", "latin", [
        _item(M[6], "oats", "oats"),
        _item(M[6], "thoda cheeni", "cheeni", qty="thoda", vague=True),
    ]),
}

INTAKE = {
    M[5].lower(): _intake("english", "latin", "gibberish"),
}

# One combined clarification message per demo message, in the customer's language and script.
CLARIFIER = {
    M[1].lower(): {"message": "Bhaiya, Amul Butter 100g abhi stock mein nahi hai - neeche se koi aur option chun lijiye. "
                              "Aur tel kaunsa chahiye - Fortune Sunflower, Fortune Groundnut ya Dhara Mustard? "
                              "Neeche tap kijiye ya likh dijiye."},
    M[2].lower(): {"message": "कौन सा चावल चाहिए - Basmati या Kolam? नीचे से चुन लीजिए या लिखकर बता दीजिए।"},
    M[3].lower(): {"message": "कोणता तांदूळ हवा - Basmati की Kolam? खाली निवडा किंवा लिहून सांगा."},
    M[4].lower(): {"message": "Amul Butter 100g abhi stock mein nahi hai - neeche se koi aur option chun lijiye "
                              "ya likh dijiye."},
    M[6].lower(): {"message": "Oats abhi hamare paas nahi mile. Aur cheeni kitni chahiye - 1 kilo, 2 kilo? "
                              "Bata dijiye."},
}

FIXTURES = {"parser": PARSER, "intake": INTAKE, "clarifier": CLARIFIER}

"""Regression tests for conversation state: stale questions, duplicate lines, quantities, "ruko", language.

Each test is a multi-message conversation. Only the parser's JSON is canned (LLM_MOCK fixtures); matching, stock,
status and the bot replies come from the real code and database.
"""
from decimal import Decimal

import pytest

from app.llm import fixtures
from tests.test_orchestrator import M, chat, client, mock_llm, send, shop, stock_of  # noqa: F401  (fixtures)


def item(raw, name, qty=None, unit=None, vague=False, brand=None):
    return {"raw_text": raw, "name_guess": name, "brand_guess": brand, "quantity_text": qty, "unit_text": unit,
            "is_vague": vague}


def say(chat, monkeypatch, text, items=None, intent="add_items", language="hinglish", script="latin"):
    """Send `text` after registering what the (mock) parser returns for it."""
    if items is not None or intent != "add_items":
        monkeypatch.setitem(fixtures.FIXTURES["parser"], text.lower(), {
            "language": language, "script": script, "intent": intent, "items": items or []})
    r = send(chat, text)
    assert r.status_code == 200, r.text
    return r.json()


def live(order):
    return [i for i in order["items"] if i["status"] != "removed"]


def open_clars(order):
    return [c for c in order["clarifications"] if c["resolved_at"] is None]


def word_of(order, clar):
    return next(i["name_guess"] for i in order["items"] if i["id"] == clar["order_item_id"])


def bot(body):
    """The bot's text reply (the bill card, type "bill", is posted after it and is not a reply)."""
    return [m for m in body["messages"] if m["type"] != "bill"][-1]["content"]


def text_msgs(body):
    return [m for m in body["messages"] if m["type"] != "bill"]


def answer(chat, clar, **body):
    r = client.post(f"/conversations/{chat['id']}/clarifications/{clar['id']}/answer", json=body, headers=chat["headers"])
    assert r.status_code == 200, r.text
    return r.json()


# ---- "ruko" ---------------------------------------------------------------------------------------------
def test_ruko_keeps_the_ready_order_and_does_not_reset(chat, monkeypatch):
    b1 = say(chat, monkeypatch, "Mother Dairy Butter 100g", [item("Mother Dairy Butter 100g", "Mother Dairy Butter 100g", "1")])
    assert b1["order"]["status"] == "awaiting_confirmation" and "Order ready" in bot(b1)
    before = b1["order"]

    b2 = say(chat, monkeypatch, "ruko")
    assert "aaram se batao" in bot(b2) and "current order" in bot(b2)
    assert "grocery orders mein madad" not in bot(b2)  # not the generic welcome
    assert b2["order"]["id"] == before["id"] and b2["order"]["status"] == "awaiting_confirmation"
    assert [(i["id"], i["status"], i["product_name"]) for i in b2["order"]["items"]] == [
        (i["id"], i["status"], i["product_name"]) for i in before["items"]]
    assert [a["agent"] for a in b2["agent_runs"]] == ["intake", "messaging"]  # no LLM call, no parsing

    b3 = say(chat, monkeypatch, "ruko ek minute bhai")
    assert "aaram se batao" in bot(b3)


@pytest.mark.parametrize("text, expected", [
    ("रुको", "ठीक है भाई"),
    ("थांबा", "ठीक आहे"),
    ("wait", "take your time"),
])
def test_wait_in_other_languages(chat, monkeypatch, text, expected):
    body = say(chat, monkeypatch, text)
    assert expected in bot(body)


def test_wait_with_nothing_ordered_yet_does_not_claim_an_order(chat, monkeypatch):
    body = say(chat, monkeypatch, "ruko")
    assert body["order"] is None and "current order" not in bot(body) and "aaram se batao" in bot(body)


def test_ruko_with_an_item_in_the_same_message_is_still_an_order(chat, monkeypatch):
    body = say(chat, monkeypatch, "ruko 2 kilo atta", [item("2 kilo atta", "atta", "2", "kilo")])
    assert live(body["order"])[0]["product_name"] == "Atta (Loose)"


def test_pending_chips_survive_an_off_topic_message(chat, monkeypatch):
    b1 = say(chat, monkeypatch, "tel chahiye", [item("tel", "tel")])
    ids = text_msgs(b1)[-1]["meta"]["clarification_ids"]
    assert ids
    for text in ("ruko", "kya haal hai"):
        if text != "ruko":
            monkeypatch.setitem(fixtures.FIXTURES["parser"], text, {"language": "hinglish", "script": "latin", "intent": "other", "items": []})
        b = say(chat, monkeypatch, text)
        assert text_msgs(b)[-1]["meta"]["clarification_ids"] == ids
        assert len(open_clars(b["order"])) == 1


# ---- stale questions ------------------------------------------------------------------------------------
def test_new_message_does_not_repeat_old_questions(chat, monkeypatch):
    b1 = say(chat, monkeypatch, "thoda cheeni", [item("thoda cheeni", "cheeni", "thoda", vague=True)])
    assert "cheeni" in bot(b1).lower()

    b2 = say(chat, monkeypatch, "pav kilo coriander", [item("pav kilo coriander", "coriander", "pav", "kilo")], language="english")
    text = bot(b2).lower()
    assert "coriander" in text and "cheeni" not in text and "sugar" not in text
    items = {i["name_guess"]: i for i in b2["order"]["items"]}
    assert items["coriander"]["status"] == "unmatched" and Decimal(items["coriander"]["quantity_value"]) == Decimal("0.25")
    # the sugar question is still pending (chips + draft), just not narrated again
    assert items["cheeni"]["status"] == "vague_qty"
    assert len(text_msgs(b2)[-1]["meta"]["clarification_ids"]) == 2

    b3 = say(chat, monkeypatch, "दीड किलो तांदूळ", [item("दीड किलो तांदूळ", "तांदूळ", "दीड", "किलो")], language="marathi", script="devanagari")
    text = bot(b3).lower()
    assert "तांदूळ" in text and "cheeni" not in text and "coriander" not in text
    rice = next(i for i in b3["order"]["items"] if i["name_guess"] == "तांदूळ")
    assert rice["status"] == "ambiguous" and Decimal(rice["quantity_value"]) == Decimal("1.5")
    assert len(open_clars(b3["order"])) == 3  # nothing was silently dropped
    assert not any(word_of(b3["order"], c) not in ("cheeni", "coriander", "तांदूळ") for c in open_clars(b3["order"]))


def test_reminder_when_the_new_message_raises_no_question(chat, monkeypatch):
    say(chat, monkeypatch, "thoda cheeni", [item("thoda cheeni", "cheeni", "thoda", vague=True)])
    b = say(chat, monkeypatch, "2 kilo atta", [item("2 kilo atta", "atta", "2", "kilo")])
    assert b["order"]["status"] == "needs_clarification"
    assert "cheeni" in bot(b) and "Order ready" not in bot(b)  # a short reminder, not a full re-ask
    assert [a["agent"] for a in b["agent_runs"]][-2:] == ["clarifier", "messaging"]
    assert b["agent_runs"][-2]["status"] == "skipped"


# ---- quantities and several items -----------------------------------------------------------------------
def test_quantity_is_kept_while_waiting_for_the_rice_choice(chat, monkeypatch):
    b = say(chat, monkeypatch, "Bhaiya do kilo chawal dena", [item("do kilo chawal", "chawal", "do", "kilo")])
    rice = live(b["order"])[0]
    assert rice["status"] == "ambiguous" and Decimal(rice["quantity_value"]) == 2 and rice["unit"] == "kg"
    assert "kitna" not in bot(b).lower()  # the quantity is known: never asked again
    assert [c["kind"] for c in open_clars(b["order"])] == ["ambiguous_product"]

    clar = open_clars(b["order"])[0]
    basmati = next(o for o in clar["options"] if "Basmati" in o["label"])
    done = answer(chat, clar, option_product_id=basmati["product_id"])
    rice = live(done["order"])[0]
    assert rice["status"] == "matched" and rice["product_name"] == "Basmati Rice (Loose)"
    assert Decimal(rice["product_qty"]) == 2  # still 2 kg
    assert done["order"]["status"] == "awaiting_confirmation" and not open_clars(done["order"])


def test_both_items_and_quantities_are_kept_while_waiting_for_rice(chat, monkeypatch):
    b = say(chat, monkeypatch, "Mujhe do kilo chawal aur ek kilo chini chahiye", [
        item("do kilo chawal", "chawal", "do", "kilo"), item("ek kilo chini", "chini", "ek", "kilo")])
    items = {i["name_guess"]: i for i in b["order"]["items"]}
    assert items["chini"]["status"] == "matched" and Decimal(items["chini"]["product_qty"]) == 1
    assert items["chawal"]["status"] == "ambiguous" and Decimal(items["chawal"]["quantity_value"]) == 2
    assert b["order"]["status"] == "needs_clarification"
    assert "chini" not in bot(b).lower() and "kitna" not in bot(b).lower()

    clar = open_clars(b["order"])[0]
    kolam = next(o for o in clar["options"] if "Kolam" in o["label"])
    done = answer(chat, clar, option_product_id=kolam["product_id"])["order"]
    by = {i["name_guess"]: i for i in live(done)}
    assert Decimal(by["chawal"]["product_qty"]) == 2 and by["chawal"]["product_name"] == "Kolam Rice (Loose)"
    assert Decimal(by["chini"]["product_qty"]) == 1 and by["chini"]["product_name"] == "Sugar (Loose)"
    assert done["status"] == "awaiting_confirmation"
    assert set(by) == {"chawal", "chini"}  # nothing the customer did not ask for


# ---- duplicate / replaced lines -------------------------------------------------------------------------
def test_saying_the_same_unresolved_item_again_replaces_it(chat, monkeypatch):
    say(chat, monkeypatch, "दीड किलो तांदूळ", [item("दीड किलो तांदूळ", "तांदूळ", "दीड", "किलो")], language="marathi", script="devanagari")
    say(chat, monkeypatch, "Bhaiya do kilo chawal dena", [item("do kilo chawal", "chawal", "do", "kilo")])
    b = say(chat, monkeypatch, "Mujhe do kilo chawal aur ek kilo chini chahiye", [
        item("do kilo chawal", "chawal", "do", "kilo"), item("ek kilo chini", "chini", "ek", "kilo")])
    order = b["order"]
    rice = [i for i in live(order) if i["status"] == "ambiguous"]
    assert len(rice) == 1 and rice[0]["name_guess"] == "chawal" and Decimal(rice[0]["quantity_value"]) == 2
    assert len(open_clars(order)) == 1  # one question about rice, not three
    assert sum(1 for i in order["items"] if i["status"] == "removed") == 2  # the two older rice lines


def test_later_exact_quantity_resolves_the_vague_one(chat, monkeypatch):
    say(chat, monkeypatch, "thoda cheeni", [item("thoda cheeni", "cheeni", "thoda", vague=True)])
    b = say(chat, monkeypatch, "ek kilo chini", [item("ek kilo chini", "chini", "ek", "kilo")])
    assert [i["name_guess"] for i in live(b["order"])] == ["chini"]
    assert not open_clars(b["order"]) and b["order"]["status"] == "awaiting_confirmation"
    assert "Order ready" in bot(b)


def test_naming_an_offered_alternative_replaces_the_out_of_stock_item(chat, monkeypatch):
    b1 = say(chat, monkeypatch, "ek Amul butter", [item("ek Amul butter", "butter", "ek", brand="Amul")])
    assert live(b1["order"])[0]["status"] == "out_of_stock"
    b2 = say(chat, monkeypatch, "Mother Dairy Butter 100g", [item("Mother Dairy Butter 100g", "Mother Dairy Butter 100g", "1")])
    assert [i["product_name"] for i in live(b2["order"])] == ["Mother Dairy Butter 100g"]
    assert not open_clars(b2["order"]) and b2["order"]["status"] == "awaiting_confirmation"


def test_matched_lines_are_not_merged(chat, monkeypatch):
    say(chat, monkeypatch, "2 kilo atta", [item("2 kilo atta", "atta", "2", "kilo")])
    b = say(chat, monkeypatch, "1 kilo atta", [item("1 kilo atta", "atta", "1", "kilo")])
    assert len(live(b["order"])) == 2  # settled lines stay; changing quantities is Stage 5


# ---- answering vs a new item ----------------------------------------------------------------------------
def test_a_reply_naming_another_product_is_not_applied_to_the_open_question(chat, monkeypatch):
    say(chat, monkeypatch, "thoda cheeni", [item("thoda cheeni", "cheeni", "thoda", vague=True)])
    # a parser that wrongly calls this an answer to the sugar question
    b = say(chat, monkeypatch, "दीड किलो तांदूळ", [], intent="answer_clarification", language="hindi", script="devanagari")
    sugar = live(b["order"])[0]
    assert sugar["status"] == "vague_qty" and sugar["quantity_value"] is None  # 1.5 kg was NOT given to sugar
    assert len(open_clars(b["order"])) == 1


def test_a_real_quantity_answer_still_works(chat, monkeypatch):
    b = say(chat, monkeypatch, "thoda cheeni", [item("thoda cheeni", "cheeni", "thoda", vague=True)])
    b = say(chat, monkeypatch, "2 kilo", [], intent="answer_clarification")
    sugar = live(b["order"])[0]
    assert sugar["status"] == "matched" and Decimal(sugar["product_qty"]) == 2
    assert b["order"]["status"] == "awaiting_confirmation"


# ---- language consistency -------------------------------------------------------------------------------
def test_reply_language_is_stable_across_messages(chat, monkeypatch):
    b1 = say(chat, monkeypatch, "thoda cheeni", [item("thoda cheeni", "cheeni", "thoda", vague=True)])
    assert "kitni" in bot(b1) or "kitna" in bot(b1)  # Hinglish
    # a parser that guesses "english" for "pav kilo coriander" must not flip the chat to English
    b2 = say(chat, monkeypatch, "pav kilo coriander", [item("pav kilo coriander", "coriander", "pav", "kilo")], language="english")
    assert "hamare paas nahi" in bot(b2)
    state = client.get(f"/conversations/{chat['id']}", headers=chat["headers"]).json()
    assert state["conversation"]["language"] == "hinglish"


def test_english_hindi_and_marathi_each_get_their_own_language(chat, monkeypatch):
    b = say(chat, monkeypatch, "I want 2 kg oats", [item("2 kg oats", "oats", "2", "kg")], language="english")
    assert "We couldn't find oats" in bot(b)
    b = say(chat, monkeypatch, "एक किलो ओट्स", [item("एक किलो ओट्स", "ओट्स", "एक", "किलो")], language="hindi", script="devanagari")
    assert "हमारे पास नहीं मिला" in bot(b)
    b = say(chat, monkeypatch, "अर्धा किलो ओट्स आणि मला", [item("अर्धा किलो ओट्स", "ओट्स", "अर्धा", "किलो")], language="marathi", script="devanagari")
    assert "आमच्याकडे मिळाले नाही" in bot(b)


def test_restating_an_item_as_an_answer_updates_it_and_keeps_the_quantity(chat, monkeypatch):
    """The real parser called "Bhaiya do kilo chawal dena" an answer (no items) while the rice question was open."""
    say(chat, monkeypatch, "दीड किलो तांदूळ", [item("दीड किलो तांदूळ", "तांदूळ", "दीड", "किलो")], language="marathi", script="devanagari")
    b = say(chat, monkeypatch, "Bhaiya do kilo chawal dena", [], intent="answer_clarification")
    assert "Samajh nahi aaya" not in bot(b)
    rice = [i for i in live(b["order"]) if i["status"] == "ambiguous"]
    assert len(rice) == 1 and Decimal(rice[0]["quantity_value"]) == 2  # the new quantity, not 1.5 and not asked again
    assert len(open_clars(b["order"])) == 1 and "kitna" not in bot(b).lower()

    done = answer(chat, open_clars(b["order"])[0], option_product_id=open_clars(b["order"])[0]["options"][0]["product_id"])
    assert Decimal(live(done["order"])[0]["product_qty"]) == 2

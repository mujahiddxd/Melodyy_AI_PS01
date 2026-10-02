"""Availability questions ("Shakkar hai?") are answered from the shop catalog + DB stock and never touch the order.

Regression: the real parser returned intent "status_query" with no items for "Shakkar hai?", which fell into the
"unsupported intent" branch ("Ye option abhi aa raha hai ..."). The same intent with an item used to ADD the product
to the order. These tests run the real API/service flow; only the parser's JSON is canned.
"""
from decimal import Decimal

import pytest
from sqlalchemy import select, update

from app.db import SessionLocal
from app.llm import fixtures
from app.models import Order, OrderItem, Product
from tests.test_conversation_state import answer, bot, item, live, open_clars, say  # noqa: F401
from tests.test_orchestrator import M, chat, client, mock_llm, send, shop, stock_of  # noqa: F401

UNSUPPORTED = "Ye option abhi aa raha hai"


def ask(chat, monkeypatch, text, intent="status_query", items=None, **kw):
    return say(chat, monkeypatch, text, items or [], intent=intent, **kw)


def rows(chat):
    with SessionLocal() as db:
        return db.scalar(select(Order.id).where(Order.conversation_id == chat["id"]))


def test_shakkar_hai_with_the_exact_parser_output_from_the_bug(chat, monkeypatch):
    """status_query + no items (what the real LLM returned) -> answered from the catalog, not 'coming soon'."""
    before = stock_of(chat["shop"]["id"])
    b = ask(chat, monkeypatch, "Shakkar hai?")
    assert UNSUPPORTED not in bot(b)
    assert "Sugar (Loose)" in bot(b) and "₹46" in bot(b) and "available hai" in bot(b)
    assert b["order"] is None and rows(chat) is None  # nothing added, no order created
    assert [a["agent"] for a in b["agent_runs"]] == ["intake", "parser", "inventory", "messaging"]
    inv = b["agent_runs"][2]
    assert inv["output"][0]["found"] and inv["output"][0]["products"][0]["name"] == "Sugar (Loose)"
    assert stock_of(chat["shop"]["id"]) == before  # read only


def test_parser_labelled_availability_query(chat, monkeypatch):
    b = ask(chat, monkeypatch, "Shakkar hai?", "availability_query", [item("Shakkar", "Shakkar")])
    assert "Sugar (Loose)" in bot(b) and b["order"] is None


def test_a_question_with_an_item_is_not_added_to_the_order(chat, monkeypatch):
    """status_query WITH an item used to fall through to the order pipeline and add 'atta' as an ambiguous line."""
    b = ask(chat, monkeypatch, "kya aapke paas atta hai", "status_query", [item("atta", "atta")])
    assert b["order"] is None and rows(chat) is None
    assert "Atta (Loose)" in bot(b) and "Aashirvaad Atta 1kg" in bot(b) and "Aashirvaad Atta 5kg" in bot(b)
    assert "kaunsa atta chahiye" not in bot(b).lower()


def test_existing_order_is_untouched_by_a_question(chat, monkeypatch):
    b1 = say(chat, monkeypatch, "thoda cheeni", [item("thoda cheeni", "cheeni", "thoda", vague=True)])
    b1 = say(chat, monkeypatch, "2 kilo atta", [item("2 kilo atta", "atta", "2", "kilo")])
    before = [(i["id"], i["status"], i["quantity_value"]) for i in b1["order"]["items"]]
    ids = b1["messages"][-1]["meta"]["clarification_ids"]

    b2 = ask(chat, monkeypatch, "Shakkar hai?")
    assert "Sugar (Loose)" in bot(b2)
    assert [(i["id"], i["status"], i["quantity_value"]) for i in b2["order"]["items"]] == before
    assert b2["order"]["status"] == b1["order"]["status"] == "needs_clarification"
    assert b2["messages"][-1]["meta"]["clarification_ids"] == ids  # the pending chips stay visible
    assert len(open_clars(b2["order"])) == len(ids)


def test_uses_live_database_stock_not_a_cached_answer(chat, monkeypatch):
    sid = chat["shop"]["id"]
    assert "available hai" in bot(ask(chat, monkeypatch, "Shakkar hai?"))
    with SessionLocal() as db:
        db.execute(update(Product).where(Product.shop_id == sid, Product.name == "Sugar (Loose)").values(stock_qty=0))
        db.commit()
    out = bot(ask(chat, monkeypatch, "Shakkar hai?"))
    assert "stock mein nahi" in out and "Haan" not in out
    with SessionLocal() as db:
        db.execute(update(Product).where(Product.shop_id == sid, Product.name == "Sugar (Loose)").values(stock_qty=Decimal("2")))
        db.commit()
    assert "sirf 2 kg bacha" in bot(ask(chat, monkeypatch, "Shakkar hai?"))  # low stock quoted from the DB


def test_one_pack_out_of_stock_is_flagged_and_the_other_pack_is_offered(chat, monkeypatch):
    b = ask(chat, monkeypatch, "Amul butter hai?", "availability_query", [item("Amul butter", "butter", brand="Amul")])
    out = bot(b)
    assert "Amul Butter 100g (₹54) (abhi stock mein nahi)" in out and "Amul Butter 500g (₹275)" in out
    assert b["order"] is None


def test_everything_out_of_stock_offers_in_stock_alternatives_from_the_database(chat, monkeypatch):
    with SessionLocal() as db:
        db.execute(update(Product).where(Product.shop_id == chat["shop"]["id"], Product.name == "Amul Butter 500g").values(stock_qty=0))
        db.commit()
    b = ask(chat, monkeypatch, "Amul butter hai?", "availability_query", [item("Amul butter", "butter", brand="Amul")])
    out = bot(b)
    assert "stock mein nahi hai" in out and "Amul Butter 100g" in out and "Amul Butter 500g" in out
    assert "Mother Dairy Butter 100g (₹56)" in out and "Haan" not in out  # the alternative, price from the DB
    assert b["order"] is None


def test_low_stock_is_reported(chat, monkeypatch):
    out = bot(ask(chat, monkeypatch, "maggi hai?", "availability_query", [item("maggi", "maggi")]))
    assert "Maggi Noodles 70g" in out and "sirf 3 bacha" in out


def test_generic_word_lists_every_matching_product(chat, monkeypatch):
    out = bot(ask(chat, monkeypatch, "tel hai?"))
    for name in ("Fortune Sunflower Oil 1L", "Fortune Groundnut Oil 1L", "Dhara Mustard Oil 1L"):
        assert name in out
    assert "₹155" in out and "₹190" in out and "₹180" in out


def test_unknown_product_is_not_found_and_not_added(chat, monkeypatch):
    b = ask(chat, monkeypatch, "oats hai?", "availability_query", [item("oats", "oats")])
    assert "oats hamare paas nahi mila" in bot(b) and b["order"] is None and rows(chat) is None


@pytest.mark.parametrize("text, lang, script, expected", [
    ("चीनी है?", "hindi", "devanagari", "उपलब्ध है"),
    ("साखर आहे का?", "marathi", "devanagari", "उपलब्ध आहे"),
    ("do you have sugar", "english", "latin", "is available"),
])
def test_other_languages(chat, monkeypatch, text, lang, script, expected):
    b = ask(chat, monkeypatch, text, language=lang, script=script)
    assert expected in bot(b) and "Sugar (Loose)" in bot(b) and b["order"] is None


def test_an_order_status_question_is_still_unsupported_not_an_availability_answer(chat, monkeypatch):
    b = ask(chat, monkeypatch, "mera order kahan hai")
    assert UNSUPPORTED in bot(b)


def test_ordering_still_works_after_a_question(chat, monkeypatch):
    ask(chat, monkeypatch, "Shakkar hai?")
    b = say(chat, monkeypatch, "ek kilo chini", [item("ek kilo chini", "chini", "ek", "kilo")])
    assert live(b["order"])[0]["product_name"] == "Sugar (Loose)" and b["order"]["status"] == "awaiting_confirmation"

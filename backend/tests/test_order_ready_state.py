"""Regression: after "Order ready hai ✅ Bill neeche hai..." every new message is processed on its own (exactly once) and the
reply says what happened.

    Bot: "Order ready hai ✅ Bill neeche hai..."  Customer: "ek kilo buscuit hai"  Bot: "Order ready hai ✅ Bill neeche hai..."

Traced cause: the message WAS processed, but (1) whether "hai" meant "do you have" or "I want" was left to the LLM, which
varies run to run, and when it read an order the biscuit was added silently, and (2) the fixed "order ready" sentence did
not name what changed, so a changed draft looked like a repeated reply. Billing/confirming is Stage 4, so a confirmation
points to the bill card's Confirm button (nothing is confirmed from free text).
"""
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.db import SessionLocal
from app.llm import fixtures
from app.models import AgentRun, Message
from tests.test_conversation_state import text_msgs, answer, bot, item, live, open_clars, say  # noqa: F401
from tests.test_orchestrator import chat, client, mock_llm, send, shop, stock_of  # noqa: F401

READY = "Order ready hai ✅ Bill neeche hai, dekh ke confirm kijiye."
BISCUIT = item("ek kilo buscuit", "buscuit", "ek", "kilo")


@pytest.fixture
def ready(chat, monkeypatch):
    """A conversation whose draft is ready: 2 kg atta, bot said "Order ready hai ✅ Bill neeche hai..."."""
    b = say(chat, monkeypatch, "2 kilo atta", [item("2 kilo atta", "atta", "2", "kilo")])
    assert bot(b) == f"Jod diya: Atta (Loose) 2 kg. {READY}"
    assert b["order"]["status"] == "awaiting_confirmation"
    return {"chat": chat, "order": b["order"], "last": bot(b), "mp": monkeypatch}


def snapshot(order):
    return [(i["id"], i["status"], i["product_name"], i["quantity_value"], i["product_qty"]) for i in order["items"]]


def bot_messages(chat):
    state = client.get(f"/conversations/{chat['id']}", headers=chat["headers"]).json()
    return [m["content"] for m in state["messages"] if m["sender"] == "bot" and m["type"] != "bill"], state


# ---- interpretation 1: "ek kilo buscuit hai" is a QUESTION -----------------------------------------------
@pytest.mark.parametrize("label, items", [
    ("availability_query", [BISCUIT]),
    ("new_order", [BISCUIT]),      # the LLM read it as an order: the words say question, so it is a question
    ("add_items", [BISCUIT]),
    ("status_query", []),          # the LLM gave an intent but no items at all
])
def test_biscuit_hai_is_an_availability_question_not_an_order(ready, label, items):
    chat, mp = ready["chat"], ready["mp"]
    before_stock = stock_of(chat["shop"]["id"])
    b = say(chat, mp, "ek kilo buscuit hai", items, intent=label)

    out = bot(b)
    assert out != ready["last"] and READY not in out  # NOT a repeat of the previous bot message
    assert "Parle-G 50g" in out and "Parle-G 250g" in out and "₹25" in out  # real catalog + prices
    assert "1 kg ke liye Parle-G 250g ×4 mil jayega" in out  # the asked quantity, from DB stock
    # the draft is exactly as before: nothing was added
    assert snapshot(b["order"]) == snapshot(ready["order"]) and b["order"]["status"] == "awaiting_confirmation"
    assert [a["agent"] for a in b["agent_runs"]] == ["intake", "parser", "inventory", "messaging"]
    assert stock_of(chat["shop"]["id"]) == before_stock  # read only


def test_quantity_is_read_from_the_message_when_the_parser_drops_it(ready):
    """The real parser sometimes returns the item without its quantity."""
    b = say(ready["chat"], ready["mp"], "ek kilo buscuit hai", [item("buscuit", "buscuit")], intent="availability_query")
    assert "1 kg ke liye Parle-G 250g ×4 mil jayega" in bot(b) and snapshot(b["order"]) == snapshot(ready["order"])


def test_question_form_with_question_mark(ready):
    b = say(ready["chat"], ready["mp"], "Ek kilo biscuit hai?", [item("Ek kilo biscuit", "biscuit", "Ek", "kilo")],
            intent="availability_query")
    assert "mil jayega" in bot(b) and snapshot(b["order"]) == snapshot(ready["order"])


def test_availability_quotes_the_live_stock_for_the_asked_quantity(ready):
    from sqlalchemy import update
    from app.models import Product

    with SessionLocal() as db:
        db.execute(update(Product).where(Product.shop_id == ready["chat"]["shop"]["id"], Product.name == "Parle-G 250g")
                   .values(stock_qty=Decimal("2")))
        db.commit()
    b = say(ready["chat"], ready["mp"], "ek kilo buscuit hai", [BISCUIT], intent="availability_query")
    assert "itna stock nahi hai" in bot(b) and "sirf 2" in bot(b)
    assert snapshot(b["order"]) == snapshot(ready["order"])


# ---- interpretation 2: "ek kilo buscuit de do" is an ORDER -----------------------------------------------
@pytest.mark.parametrize("label", ["add_items", "new_order", "availability_query"])  # even if the LLM says "question"
def test_biscuit_de_do_is_an_order_and_the_reply_says_what_was_added(ready, label):
    chat, mp = ready["chat"], ready["mp"]
    before_stock = stock_of(chat["shop"]["id"])
    b = say(chat, mp, "ek kilo buscuit de do", [BISCUIT], intent=label)

    out = bot(b)
    assert out != ready["last"]  # never the same sentence as the previous reply
    assert out == f"Jod diya: Parle-G 250g ×4. {READY}"  # says what changed and still offers the bill
    names = {i["product_name"]: i for i in live(b["order"])}
    assert set(names) == {"Atta (Loose)", "Parle-G 250g"}  # existing item kept, nothing else appeared
    assert Decimal(names["Atta (Loose)"]["product_qty"]) == 2  # quantity of the existing line unchanged
    assert Decimal(names["Parle-G 250g"]["product_qty"]) == 4
    assert b["order"]["status"] == "awaiting_confirmation" and not open_clars(b["order"])
    assert stock_of(chat["shop"]["id"]) == before_stock  # stock is deducted only at confirmation (Stage 4)


def test_existing_lines_are_untouched_when_an_item_is_added(ready):
    b = say(ready["chat"], ready["mp"], "ek kilo buscuit de do", [BISCUIT], intent="add_items")
    old = ready["order"]["items"][0]
    now = next(i for i in b["order"]["items"] if i["id"] == old["id"])
    assert (now["status"], now["quantity_value"], now["product_qty"]) == (old["status"], old["quantity_value"], old["product_qty"])


# ---- confirmation ---------------------------------------------------------------------------------------
def test_explicit_confirmation_is_recognised_and_does_not_change_the_draft(ready):
    b = say(ready["chat"], ready["mp"], "Haan, bill bana do")
    out = bot(b)
    assert out != ready["last"] and "Confirm order" in out and "Atta (Loose) 2 kg" in out
    assert b["order"]["status"] == "awaiting_confirmation"  # Stage 4 will confirm; nothing is confirmed here
    assert snapshot(b["order"]) == snapshot(ready["order"])
    assert [a["agent"] for a in b["agent_runs"]] == ["intake", "messaging"]  # no LLM needed for a clear "haan"


def test_confirmation_the_parser_recognises_is_handled_the_same_way(ready):
    b = say(ready["chat"], ready["mp"], "sab theek hai, bill ban jayega na", [], intent="confirm")
    assert "Confirm order" in bot(b) and b["order"]["status"] == "awaiting_confirmation"
    assert "Ye option abhi aa raha hai" not in bot(b)


def test_confirmation_with_a_pending_question_asks_for_the_answer_first(chat, monkeypatch):
    b1 = say(chat, monkeypatch, "thoda cheeni", [item("thoda cheeni", "cheeni", "thoda", vague=True)])
    b = say(chat, monkeypatch, "haan bill bana do", [], intent="confirm")
    assert "Pehle in items ka jawab" in bot(b) and "cheeni" in bot(b)
    assert b["order"]["status"] == "needs_clarification"
    assert text_msgs(b)[-1]["meta"]["clarification_ids"] == text_msgs(b1)[-1]["meta"]["clarification_ids"]


def test_no_order_means_nothing_to_confirm(chat, monkeypatch):
    b = say(chat, monkeypatch, "haan bill bana do")
    assert b["order"] is None and "koi item nahi" in bot(b)


# ---- rejection / delay ----------------------------------------------------------------------------------
@pytest.mark.parametrize("text", ["Nahi", "nahi bhai", "abhi nahi", "rehne do"])
def test_rejecting_the_bill_keeps_the_draft(ready, text):
    b = say(ready["chat"], ready["mp"], text)
    assert "order abhi confirm nahi karte" in bot(b) and "Atta (Loose) 2 kg" in bot(b) and bot(b) != ready["last"]
    assert snapshot(b["order"]) == snapshot(ready["order"]) and b["order"]["status"] == "awaiting_confirmation"


def test_ruko_keeps_the_draft(ready):
    b = say(ready["chat"], ready["mp"], "Ruko")
    assert "current order yahin rakhta hoon" in bot(b) and bot(b) != ready["last"]
    assert snapshot(b["order"]) == snapshot(ready["order"])


def test_nahi_to_an_open_question_skips_that_item_instead_of_cancelling_everything(chat, monkeypatch):
    say(chat, monkeypatch, "2 kilo atta", [item("2 kilo atta", "atta", "2", "kilo")])
    say(chat, monkeypatch, "thoda cheeni", [item("thoda cheeni", "cheeni", "thoda", vague=True)])
    b = say(chat, monkeypatch, "nahi", [], intent="cancel")
    by = {i["name_guess"]: i["status"] for i in b["order"]["items"]}
    assert by == {"atta": "matched", "cheeni": "removed"}  # only the item we asked about, the rest is kept
    assert b["order"]["status"] == "awaiting_confirmation"


def test_an_order_status_question_and_a_real_cancel_are_still_not_confused(ready):
    b = say(ready["chat"], ready["mp"], "order cancel kar do", [], intent="cancel")
    assert "Ye option abhi aa raha hai" in bot(b) and snapshot(b["order"]) == snapshot(ready["order"])


# ---- every message is processed exactly once, and never answered with the previous reply ------------------
def test_the_whole_conversation_each_message_once_and_no_repeated_reply(chat, monkeypatch):
    texts = [
        ("2 kilo atta", [item("2 kilo atta", "atta", "2", "kilo")], "new_order"),
        ("ek kilo buscuit hai", [BISCUIT], "new_order"),
        ("ek kilo buscuit de do", [BISCUIT], "add_items"),
        ("ruko", None, None),
        ("Haan, bill bana do", None, None),
        ("Nahi", None, None),
    ]
    for text, items, intent in texts:
        say(chat, monkeypatch, text, items, intent=intent) if items is not None else say(chat, monkeypatch, text)

    replies, state = bot_messages(chat)
    assert len(replies) == len(texts) and len(set(replies)) == len(texts)  # six messages, six different replies
    customer = [m for m in state["messages"] if m["sender"] == "customer"]
    assert [m["content"] for m in customer] == [t[0] for t in texts]  # each message stored once, in order
    with SessionLocal() as db:
        for m in customer:
            n = db.scalar(select(func.count()).select_from(AgentRun).where(AgentRun.message_id == m["id"], AgentRun.agent == "intake"))
            assert n == 1  # processed exactly once
            bots = db.scalar(select(func.count()).select_from(AgentRun).where(AgentRun.message_id == m["id"], AgentRun.agent == "messaging"))
            assert bots == 1  # and answered exactly once
    final = {i["product_name"]: i["product_qty"] for i in state["order"]["items"] if i["status"] == "matched"}
    assert set(final) == {"Atta (Loose)", "Parle-G 250g"} and state["order"]["status"] == "awaiting_confirmation"

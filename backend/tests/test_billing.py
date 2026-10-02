"""Billing agent: deterministic Decimal totals from CURRENT database prices, snapshots, bill message, agent run."""
from decimal import Decimal

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import AgentRun, Message
from tests.order_helpers import (  # noqa: F401  (fixtures)
    ATTA, SUGAR, buyer, client, conversation, mychat, owner, ready, say, set_product, set_shop, shop, stock,
)
from tests.test_orchestrator import M, send


def lines(order):
    return {i["product_name"]: i for i in order["items"] if i["status"] == "matched"}


def test_bill_totals_are_computed_by_hand_from_db_prices(ready):
    order = ready["order"]
    atta, sugar = lines(order)["Atta (Loose)"], lines(order)["Sugar (Loose)"]
    # 2 kg x 45.00 = 90.00 and 0.5 kg x 46.00 = 23.00 (seed prices); the quote is stored on the lines and the order
    assert (atta["unit_price_snapshot"], atta["line_total"]) == ("45.00", "90.00")
    assert (sugar["unit_price_snapshot"], sugar["line_total"]) == ("46.00", "23.00")
    assert order["subtotal"] == "113.00" and order["delivery_fee"] == "0.00" and order["total"] == "113.00"
    assert order["quoted_at"] is not None and order["requires_reapproval"] is False


def test_the_bill_message_is_posted_with_the_bill_json_and_logged(ready):
    bill_msgs = [m for m in ready["body"]["messages"] if m["type"] == "bill"]
    assert len(bill_msgs) == 1 and bill_msgs[0]["sender"] == "bot"
    meta = bill_msgs[0]["meta"]
    assert meta["order_id"] == ready["id"] and meta["bill"]["total"] == "113.00"
    ln = {x["name"]: x for x in meta["bill"]["lines"]}
    assert ln["Atta (Loose)"]["qty_label"] == "2 kg" and ln["Atta (Loose)"]["unit"] == "kg"
    assert ln["Atta (Loose)"]["unit_price"] == "45.00" and ln["Atta (Loose)"]["line_total"] == "90.00"
    runs = {r["agent"]: r for r in ready["body"]["agent_runs"]}
    assert runs["billing"]["status"] == "success" and runs["billing"]["output"]["total"] == "113.00"
    with SessionLocal() as db:  # the run is linked to the order
        assert db.scalar(select(AgentRun.order_id).where(AgentRun.id == runs["billing"]["id"])) == ready["id"]


def test_delivery_fee_comes_from_the_shop_and_is_added_to_the_total(mychat, monkeypatch):
    set_shop(mychat["shop"]["id"], delivery_fee=Decimal("20.00"))
    body = say(mychat, monkeypatch, "2 kilo atta aur half kilo sugar", [ATTA, SUGAR], intent="new_order")
    order = body["order"]
    assert order["subtotal"] == "113.00" and order["delivery_fee"] == "20.00" and order["total"] == "133.00"


def test_rounding_is_half_up_to_two_places(mychat, monkeypatch):
    # 0.5 kg x 33.33 = 16.665 -> 16.67 ; 2 kg x 33.33 = 66.66
    set_product(mychat["shop"]["id"], "Sugar (Loose)", price=Decimal("33.33"))
    set_product(mychat["shop"]["id"], "Atta (Loose)", price=Decimal("33.33"))
    order = say(mychat, monkeypatch, "2 kilo atta aur half kilo sugar", [ATTA, SUGAR], intent="new_order")["order"]
    assert lines(order)["Sugar (Loose)"]["line_total"] == "16.67"
    assert lines(order)["Atta (Loose)"]["line_total"] == "66.66"
    assert order["subtotal"] == "83.33" and order["total"] == "83.33"


def test_quote_endpoint_uses_current_prices_and_replaces_the_snapshot(ready):
    set_product(ready["chat"]["shop"]["id"], "Atta (Loose)", price=Decimal("50.00"))
    r = client.post(f"/orders/{ready['id']}/quote", headers=ready["chat"]["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["order"]["subtotal"] == "123.00" and body["bill"]["total"] == "123.00"
    assert lines(body["order"])["Atta (Loose)"]["unit_price_snapshot"] == "50.00"
    assert body["message"]["type"] == "bill" and body["message"]["meta"]["bill"]["total"] == "123.00"
    # two bill messages now exist in the chat; the later one is the live one
    bills = [m for m in conversation(ready["chat"])["messages"] if m["type"] == "bill"]
    assert [m["meta"]["bill"]["total"] for m in bills] == ["113.00", "123.00"]


def test_quoting_never_touches_stock(ready):
    sid = ready["chat"]["shop"]["id"]
    before = (stock(sid, "Atta (Loose)"), stock(sid, "Sugar (Loose)"))
    assert client.post(f"/orders/{ready['id']}/quote", headers=ready["chat"]["headers"]).status_code == 200
    assert (stock(sid, "Atta (Loose)"), stock(sid, "Sugar (Loose)")) == before


def test_quote_is_refused_while_a_question_is_open(mychat):
    order = send(mychat, M[1]).json()["order"]
    assert order["status"] == "needs_clarification"
    r = client.post(f"/orders/{order['id']}/quote", headers=mychat["headers"])
    assert r.status_code == 409 and r.json()["detail"]["code"] == "OPEN_CLARIFICATIONS"
    assert order["subtotal"] == "0.00"  # no bill until the order is ready


def test_quote_needs_the_owner_of_the_conversation(ready, shop):
    assert client.post(f"/orders/{ready['id']}/quote").status_code == 401
    other = client.post(f"/shops/{shop['slug']}/conversations").json()
    r = client.post(f"/orders/{ready['id']}/quote", headers={"X-Guest-Session": other["guest_session"]})
    assert r.status_code == 403


def test_a_new_bill_is_posted_when_the_order_changes_and_becomes_ready_again(ready):
    chat, mp = ready["chat"], ready["mp"]
    body = say(chat, mp, "ek kilo buscuit de do", [{"raw_text": "ek kilo buscuit", "name_guess": "buscuit",
                                                    "brand_guess": None, "quantity_text": "ek", "unit_text": "kilo",
                                                    "is_vague": False}], intent="add_items")
    assert [m["type"] for m in body["messages"]] == ["text", "text", "bill"]
    total = Decimal(body["order"]["total"])
    assert total > Decimal("113.00") and total == Decimal(body["order"]["subtotal"])
    assert Decimal(body["messages"][-1]["meta"]["bill"]["total"]) == total
    with SessionLocal() as db:
        n = db.scalar(select(func.count()).select_from(Message).where(
            Message.conversation_id == chat["id"], Message.type == "bill"))
        assert n == 2

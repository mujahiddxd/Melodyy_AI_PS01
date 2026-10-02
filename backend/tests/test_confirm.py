"""Confirm: transactional stock deduction, idempotency, STOCK_CHANGED, PRICE_CHANGED, OUT_OF_RADIUS, cancel + restore."""
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import AgentRun, Customer, Message, Order
from app.security import create_access_token
from tests.order_helpers import (  # noqa: F401  (fixtures)
    bearer, buyer, client, confirm, conversation, mychat, owner, product, ready, say, set_product, shop, stock,
)
from tests.test_orchestrator import M, send

ATTA, SUGAR = "Atta (Loose)", "Sugar (Loose)"  # the ready order: 2 kg atta (stock 40), 0.5 kg sugar (stock 50)


def stocks(sid):
    return stock(sid, ATTA), stock(sid, SUGAR)


def get_order(oid):
    with SessionLocal() as db:
        return db.get(Order, oid)


def sys_messages(chat):
    return [m for m in conversation(chat)["messages"] if m["sender"] == "system"]


# ---- the happy path ---------------------------------------------------------------------------------------
def test_stock_is_deducted_only_on_confirm_and_exactly_once(ready, buyer):
    sid = ready["chat"]["shop"]["id"]
    assert stocks(sid) == (Decimal("40"), Decimal("50"))  # nothing deducted by chatting or billing
    r = confirm(ready["id"], buyer["near"], buyer["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["newly_confirmed"] is True and body["message"] == f"Order #{1000 + ready['id']} confirmed"
    assert stocks(sid) == (Decimal("38"), Decimal("49.5"))

    o = body["order"]
    assert o["status"] == "confirmed" and o["payment_method"] == "cod" and o["payment_status"] == "cod"
    assert o["confirmed_at"] is not None and o["requires_reapproval"] is False
    # the address is snapshotted on the order
    assert o["delivery_address_text"] == "Flat 12, near the shop"
    assert (o["delivery_lat"], o["delivery_lng"]) == (18.505, 73.805)
    assert 0 < o["distance_km"] < 3 and o["total"] == "113.00"

    msgs = sys_messages(ready["chat"])
    assert len(msgs) == 1 and msgs[0]["meta"]["kind"] == "order_confirmed" and "confirm ho gaya" in msgs[0]["content"]
    assert "₹113.00" in msgs[0]["content"]

    # the customer can read it back, with its timeline
    got = client.get(f"/orders/{ready['id']}", headers=buyer["headers"]).json()
    assert got["order"]["status"] == "confirmed"
    assert [(e["from_status"], e["to_status"], e["actor"]) for e in got["timeline"]][-1] == (
        "awaiting_confirmation", "confirmed", "customer")


def test_confirming_twice_in_a_row_does_not_deduct_again(ready, buyer):
    sid = ready["chat"]["shop"]["id"]
    first = confirm(ready["id"], buyer["near"], buyer["headers"])
    second = confirm(ready["id"], buyer["near"], buyer["headers"])
    assert first.status_code == second.status_code == 200
    assert first.json()["newly_confirmed"] is True and second.json()["newly_confirmed"] is False
    assert second.json()["order"]["status"] == "confirmed"
    assert stocks(sid) == (Decimal("38"), Decimal("49.5"))
    assert len(sys_messages(ready["chat"])) == 1  # and only one confirmation message


def test_two_simultaneous_confirms_deduct_once(ready, buyer):
    sid = ready["chat"]["shop"]["id"]

    def go(_):
        with TestClient(app) as c:
            return c.post(f"/orders/{ready['id']}/confirm", json={"address_id": buyer["near"], "payment_method": "cod"},
                          headers=buyer["headers"])

    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(go, range(4)))
    assert [r.status_code for r in results] == [200] * 4
    assert sorted(r.json()["newly_confirmed"] for r in results) == [False, False, False, True]
    assert stocks(sid) == (Decimal("38"), Decimal("49.5"))
    assert len(sys_messages(ready["chat"])) == 1


def test_confirm_is_a_transaction_the_whole_order_or_nothing(ready, buyer):
    """Sugar is short, atta is fine: neither is deducted."""
    sid = ready["chat"]["shop"]["id"]
    set_product(sid, SUGAR, stock_qty=Decimal("0.2"))
    r = confirm(ready["id"], buyer["near"], buyer["headers"])
    assert r.status_code == 409
    assert stocks(sid) == (Decimal("40"), Decimal("0.2"))


# ---- STOCK_CHANGED ----------------------------------------------------------------------------------------
def test_stock_changed_between_bill_and_confirm(ready, buyer):
    chat, sid = ready["chat"], ready["chat"]["shop"]["id"]
    set_product(sid, SUGAR, stock_qty=Decimal("0"))  # the shopkeeper sets stock to 0 after the bill
    r = confirm(ready["id"], buyer["near"], buyer["headers"])
    assert r.status_code == 409, r.text
    d = r.json()["detail"]
    assert d["code"] == "STOCK_CHANGED" and "Sugar (Loose)" in d["message"]
    assert d["items"] == [{"item_id": d["items"][0]["item_id"], "product_name": SUGAR, "available_qty": "0.000"}]

    assert stocks(sid) == (Decimal("40"), Decimal("0"))  # rolled back: atta was NOT deducted either
    o = d["order"]
    assert o["status"] == "needs_clarification"
    sugar = next(i for i in o["items"] if i["product_name"] == SUGAR)
    atta = next(i for i in o["items"] if i["product_name"] == ATTA)
    assert sugar["status"] == "out_of_stock" and atta["status"] == "matched"
    clar = next(c for c in o["clarifications"] if c["order_item_id"] == sugar["id"] and c["resolved_at"] is None)
    assert clar["kind"] == "out_of_stock"
    # the chat got a question the customer can answer with chips
    bot = d["messages"][-1]
    assert bot["sender"] == "bot" and bot["meta"]["clarification_ids"] == [clar["id"]]
    state = conversation(chat)
    assert state["order"]["status"] == "needs_clarification"
    assert o["confirmed_at"] is None and o["payment_status"] is None
    # confirming again before answering: the open question blocks it
    again = confirm(ready["id"], buyer["near"], buyer["headers"])
    assert again.status_code == 409 and again.json()["detail"]["code"] == "OPEN_CLARIFICATIONS"


def test_after_stock_changed_the_customer_can_skip_the_item_and_confirm(ready, buyer):
    chat, sid = ready["chat"], ready["chat"]["shop"]["id"]
    set_product(sid, SUGAR, stock_qty=Decimal("0"))
    d = confirm(ready["id"], buyer["near"], buyer["headers"]).json()["detail"]
    clar = next(c for c in d["order"]["clarifications"] if c["resolved_at"] is None)
    r = client.post(f"/conversations/{chat['id']}/clarifications/{clar['id']}/answer", json={"text": "skip"},
                    headers=chat["headers"])
    assert r.status_code == 200, r.text
    o = r.json()["order"]
    assert o["status"] == "awaiting_confirmation" and o["total"] == "90.00"  # re-billed without the sugar
    assert r.json()["messages"][-1]["type"] == "bill"
    ok = confirm(ready["id"], buyer["near"], buyer["headers"])
    assert ok.status_code == 200
    assert stocks(sid) == (Decimal("38"), Decimal("0"))


# ---- PRICE_CHANGED ----------------------------------------------------------------------------------------
def test_price_changed_between_bill_and_confirm(ready, buyer):
    chat, sid = ready["chat"], ready["chat"]["shop"]["id"]
    set_product(sid, ATTA, price=Decimal("50.00"))
    r = confirm(ready["id"], buyer["near"], buyer["headers"])
    assert r.status_code == 409, r.text
    d = r.json()["detail"]
    assert d["code"] == "PRICE_CHANGED"
    assert d["changes"] == [{"item_id": d["changes"][0]["item_id"], "product_name": ATTA, "old_price": "45.00",
                             "new_price": "50.00"}]
    assert (d["old_total"], d["new_total"]) == ("113.00", "123.00")

    assert stocks(sid) == (Decimal("40"), Decimal("50"))  # nothing deducted
    o = d["order"]
    assert o["status"] == "awaiting_confirmation" and o["requires_reapproval"] is True and o["total"] == "123.00"
    atta = next(i for i in o["items"] if i["product_name"] == ATTA)
    assert atta["unit_price_snapshot"] == "50.00" and atta["line_total"] == "100.00"
    bill = d["messages"][-1]
    assert bill["type"] == "bill" and bill["meta"]["bill"]["total"] == "123.00"
    assert bill["meta"]["bill"]["requires_reapproval"] is True
    with SessionLocal() as db:  # the re-quote is logged as a billing run
        assert db.scalar(select(AgentRun.id).where(AgentRun.order_id == ready["id"], AgentRun.agent == "billing").order_by(AgentRun.id.desc()))

    # the customer approves by confirming the new bill: charged at the NEW price, flag cleared
    ok = confirm(ready["id"], buyer["near"], buyer["headers"])
    assert ok.status_code == 200
    assert ok.json()["order"]["total"] == "123.00" and ok.json()["order"]["requires_reapproval"] is False
    assert stocks(sid) == (Decimal("38"), Decimal("49.5"))


def test_a_price_drop_is_also_reported_not_silently_applied(ready, buyer):
    set_product(ready["chat"]["shop"]["id"], SUGAR, price=Decimal("40.00"))
    d = confirm(ready["id"], buyer["near"], buyer["headers"]).json()["detail"]
    assert d["code"] == "PRICE_CHANGED" and (d["old_total"], d["new_total"]) == ("113.00", "110.00")


# ---- OUT_OF_RADIUS and other refusals ---------------------------------------------------------------------
def test_out_of_radius_is_blocked_by_the_api(ready, buyer):
    sid = ready["chat"]["shop"]["id"]
    r = confirm(ready["id"], buyer["far"], buyer["headers"])
    assert r.status_code == 422, r.text
    d = r.json()["detail"]
    assert d["code"] == "OUT_OF_RADIUS" and d["radius_km"] == 3.0 and d["distance_km"] > 3
    assert "delivers within 3 km" in d["message"]
    assert stocks(sid) == (Decimal("40"), Decimal("50"))
    assert get_order(ready["id"]).status == "awaiting_confirmation"
    # a good address afterwards works
    assert confirm(ready["id"], buyer["near"], buyer["headers"]).status_code == 200


def test_cannot_confirm_with_someone_elses_address(ready, buyer):
    with SessionLocal() as db:
        c2 = Customer(phone=f"9{uuid.uuid4().int % 10**9:09d}", verified_at=datetime.now(timezone.utc))
        db.add(c2)
        db.commit()
        c2id = c2.id
    try:
        from app.models import CustomerAddress
        with SessionLocal() as db:
            a = CustomerAddress(customer_id=c2id, label="Home", address_text="x", lat=18.505, lng=73.805)
            db.add(a)
            db.commit()
            aid = a.id
        r = confirm(ready["id"], aid, buyer["headers"])
        assert r.status_code == 404
        # and the other customer cannot confirm MY order
        other = bearer(create_access_token(c2id, "customer"))
        r = confirm(ready["id"], aid, other)
        assert r.status_code == 403
        assert get_order(ready["id"]).status == "awaiting_confirmation"
    finally:
        with SessionLocal() as db:
            from sqlalchemy import delete
            from app.models import CustomerAddress
            db.execute(delete(CustomerAddress).where(CustomerAddress.customer_id == c2id))
            db.execute(delete(Customer).where(Customer.id == c2id))
            db.commit()


def test_confirm_needs_a_verified_customer_token(ready, buyer):
    body = {"address_id": buyer["near"], "payment_method": "cod"}
    assert client.post(f"/orders/{ready['id']}/confirm", json=body).status_code == 401
    assert client.post(f"/orders/{ready['id']}/confirm", json=body,
                       headers={"X-Guest-Session": "gs_nope"}).status_code == 401  # a guest token is not enough


def test_confirm_with_open_clarifications_is_refused(mychat, buyer):
    order = send(mychat, M[1]).json()["order"]
    r = confirm(order["id"], buyer["near"], buyer["headers"])
    assert r.status_code == 409 and r.json()["detail"]["code"] == "OPEN_CLARIFICATIONS"


def test_only_cod_is_accepted_for_now(ready, buyer):
    r = confirm(ready["id"], buyer["near"], buyer["headers"], payment_method="upi")
    assert r.status_code == 422
    assert get_order(ready["id"]).status == "awaiting_confirmation"


def test_a_guest_conversation_must_be_claimed_before_its_order_can_be_confirmed(shop, buyer, monkeypatch):
    chat = client.post(f"/shops/{shop['slug']}/conversations").json()
    g = {"id": chat["conversation"]["id"], "headers": {"X-Guest-Session": chat["guest_session"]}, "shop": shop}
    from tests.order_helpers import ATTA as A, SUGAR as S
    order = say(g, monkeypatch, "2 kilo atta aur half kilo sugar", [A, S], intent="new_order")["order"]
    r = confirm(order["id"], buyer["near"], buyer["headers"])
    assert r.status_code == 403  # not this customer's conversation yet
    assert client.post(f"/conversations/{g['id']}/claim", headers={**buyer["headers"], **g["headers"]}).status_code == 200
    assert confirm(order["id"], buyer["near"], buyer["headers"]).status_code == 200


# ---- cancel -----------------------------------------------------------------------------------------------
def test_cancelling_a_confirmed_order_restores_stock(ready, buyer, owner):
    sid = ready["chat"]["shop"]["id"]
    assert confirm(ready["id"], buyer["near"], buyer["headers"]).status_code == 200
    assert stocks(sid) == (Decimal("38"), Decimal("49.5"))
    r = client.post(f"/orders/{ready['id']}/cancel", json={"reason": "Shop closing early"}, headers=owner)
    assert r.status_code == 200 and r.json()["order"]["status"] == "cancelled"
    assert stocks(sid) == (Decimal("40"), Decimal("50"))
    # cancelling again must not restore a second time
    assert client.post(f"/orders/{ready['id']}/cancel", json={"reason": "again"}, headers=owner).status_code == 200
    assert stocks(sid) == (Decimal("40"), Decimal("50"))
    last = sys_messages(ready["chat"])[-1]
    assert last["meta"]["status"] == "cancelled" and "Shop closing early" in last["content"]


def test_cancelling_while_packing_or_out_for_delivery_also_restores_stock(ready, buyer, owner):
    sid = ready["chat"]["shop"]["id"]
    confirm(ready["id"], buyer["near"], buyer["headers"])
    for to in ("packing", "out_for_delivery"):
        assert client.post(f"/owner/orders/{ready['id']}/status", json={"to": to}, headers=owner).status_code == 200
    r = client.post(f"/owner/orders/{ready['id']}/status", json={"to": "cancelled", "note": "Customer unreachable"},
                    headers=owner)
    assert r.status_code == 200
    assert stocks(sid) == (Decimal("40"), Decimal("50"))


def test_cannot_cancel_a_delivered_order(ready, buyer, owner):
    sid = ready["chat"]["shop"]["id"]
    confirm(ready["id"], buyer["near"], buyer["headers"])
    for to in ("packing", "out_for_delivery", "delivered"):
        client.post(f"/owner/orders/{ready['id']}/status", json={"to": to}, headers=owner)
    r = client.post(f"/orders/{ready['id']}/cancel", json={"reason": "too late"}, headers=owner)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "INVALID_TRANSITION"
    assert stocks(sid) == (Decimal("38"), Decimal("49.5"))  # delivered goods stay deducted


def test_customer_can_cancel_before_confirmation_and_stock_is_untouched(ready, buyer):
    sid = ready["chat"]["shop"]["id"]
    r = client.post(f"/orders/{ready['id']}/cancel", json={}, headers=buyer["headers"])
    assert r.status_code == 200 and r.json()["order"]["status"] == "cancelled"
    assert stocks(sid) == (Decimal("40"), Decimal("50"))
    # the chat starts a fresh draft afterwards
    assert conversation(ready["chat"])["order"]["status"] == "cancelled"


def test_customer_cannot_cancel_after_confirmation(ready, buyer):
    sid = ready["chat"]["shop"]["id"]
    confirm(ready["id"], buyer["near"], buyer["headers"])
    r = client.post(f"/orders/{ready['id']}/cancel", json={}, headers=buyer["headers"])
    assert r.status_code == 409 and r.json()["detail"]["code"] == "INVALID_TRANSITION"
    assert stocks(sid) == (Decimal("38"), Decimal("49.5"))


def test_a_guest_can_cancel_their_own_draft(shop, monkeypatch):
    chat = client.post(f"/shops/{shop['slug']}/conversations").json()
    g = {"id": chat["conversation"]["id"], "headers": {"X-Guest-Session": chat["guest_session"]}, "shop": shop}
    from tests.order_helpers import ATTA as A
    order = say(g, monkeypatch, "2 kilo atta", [A], intent="new_order")["order"]
    r = client.post(f"/orders/{order['id']}/cancel", json={}, headers=g["headers"])
    assert r.status_code == 200 and r.json()["order"]["status"] == "cancelled"

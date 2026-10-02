"""Order state machine: the transition table, who may move what, events, chat messages, owner endpoints."""
import itertools

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import OrderStatusEvent
from app.models.conversation import ORDER_STATUSES
from app.services import order_state_machine as osm
from tests.order_helpers import (  # noqa: F401  (fixtures)
    bearer, buyer, client, confirm, conversation, mychat, owner, ready, say, shop,
)


# ---- the table itself ---------------------------------------------------------------------------------
EXPECTED = {
    "draft": {"needs_clarification", "awaiting_confirmation", "cancelled"},
    "needs_clarification": {"draft", "awaiting_confirmation", "cancelled"},
    "awaiting_confirmation": {"draft", "needs_clarification", "confirmed", "cancelled"},
    "confirmed": {"packing", "cancelled"},
    "packing": {"out_for_delivery", "cancelled"},
    "out_for_delivery": {"delivered", "cancelled"},
    "delivered": set(),
    "cancelled": set(),
}


@pytest.mark.parametrize("frm, to", list(itertools.product(ORDER_STATUSES, ORDER_STATUSES)))
def test_transition_table_is_exactly_the_plan(frm, to):
    assert osm.can_transition(frm, to, "system") is (to in EXPECTED[frm] and frm in osm.OPEN_STATES and to in osm.OPEN_STATES)
    anyone = any(osm.can_transition(frm, to, a) for a in ("customer", "shopkeeper", "system"))
    assert anyone is (to in EXPECTED[frm])


def test_shopkeeper_moves_are_forward_only_plus_cancel():
    assert osm.allowed_next("confirmed", "shopkeeper") == ["packing", "cancelled"]
    assert osm.allowed_next("packing", "shopkeeper") == ["out_for_delivery", "cancelled"]
    assert osm.allowed_next("out_for_delivery", "shopkeeper") == ["delivered", "cancelled"]
    assert osm.allowed_next("delivered", "shopkeeper") == [] and osm.allowed_next("cancelled", "shopkeeper") == []
    assert osm.allowed_next("awaiting_confirmation", "shopkeeper") == ["cancelled"]  # never "confirmed"


def test_customer_may_only_confirm_or_cancel_before_confirmation():
    assert osm.allowed_next("awaiting_confirmation", "customer") == ["confirmed", "cancelled"]
    assert osm.allowed_next("draft", "customer") == ["cancelled"]
    assert osm.allowed_next("confirmed", "customer") == []  # after confirmation only the shop moves it


# ---- through the API ----------------------------------------------------------------------------------
def confirmed(ready, buyer):
    r = confirm(ready["id"], buyer["near"], buyer["headers"])
    assert r.status_code == 200, r.text
    return ready["id"]


def move(owner, oid, to, note=None):
    return client.post(f"/owner/orders/{oid}/status", json={"to": to, "note": note}, headers=owner)


def events(oid):
    with SessionLocal() as db:
        return [(e.from_status, e.to_status, e.actor, e.note) for e in db.scalars(
            select(OrderStatusEvent).where(OrderStatusEvent.order_id == oid).order_by(OrderStatusEvent.id))]


def test_full_happy_path_writes_an_event_and_a_chat_message_for_every_move(ready, buyer, owner):
    oid = confirmed(ready, buyer)
    for to in ("packing", "out_for_delivery", "delivered"):
        r = move(owner, oid, to)
        assert r.status_code == 200 and r.json()["order"]["status"] == to
    ev = events(oid)
    assert ev[0] == ("draft", "awaiting_confirmation", "system", None)
    assert ev[-4:] == [
        ("awaiting_confirmation", "confirmed", "customer", None),
        ("confirmed", "packing", "shopkeeper", None),
        ("packing", "out_for_delivery", "shopkeeper", None),
        ("out_for_delivery", "delivered", "shopkeeper", None),
    ]
    msgs = [m for m in conversation(ready["chat"])["messages"] if m["sender"] == "system"]
    assert [m["meta"]["status"] for m in msgs] == ["confirmed", "packing", "out_for_delivery", "delivered"]
    assert all(m["type"] == "system" and m["meta"]["order_id"] == oid for m in msgs)
    assert f"#{1000 + oid}" in msgs[0]["content"] and "pack" in msgs[1]["content"]


@pytest.mark.parametrize("path, bad", [
    ([], "delivered"),                       # confirmed -> delivered (skips two steps)
    ([], "confirmed"),                       # confirmed -> confirmed
    (["packing"], "confirmed"),              # backwards
    (["packing"], "delivered"),              # skips out_for_delivery
    (["packing", "out_for_delivery", "delivered"], "packing"),  # nothing leaves delivered
    (["packing", "out_for_delivery", "delivered"], "cancelled"),
])
def test_invalid_owner_transitions_are_409(ready, buyer, owner, path, bad):
    oid = confirmed(ready, buyer)
    for to in path:
        assert move(owner, oid, to).status_code == 200
    before = events(oid)
    r = move(owner, oid, bad, note="because")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "INVALID_TRANSITION"
    assert events(oid) == before  # nothing was written


def test_shopkeeper_cannot_confirm_an_order_for_the_customer(ready, owner):
    r = move(owner, ready["id"], "confirmed")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "INVALID_TRANSITION"


def test_cannot_move_an_unconfirmed_order_forward(ready, owner):
    r = move(owner, ready["id"], "packing")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "INVALID_TRANSITION"


def test_cancelling_needs_a_reason_from_the_shopkeeper(ready, buyer, owner):
    oid = confirmed(ready, buyer)
    r = move(owner, oid, "cancelled")
    assert r.status_code == 422
    r = move(owner, oid, "cancelled", note="Out of gas, sorry")
    assert r.status_code == 200 and r.json()["order"]["status"] == "cancelled"
    assert events(oid)[-1] == ("confirmed", "cancelled", "shopkeeper", "Out of gas, sorry")
    last = [m for m in conversation(ready["chat"])["messages"] if m["sender"] == "system"][-1]
    assert last["meta"]["status"] == "cancelled" and "Out of gas, sorry" in last["content"]


def test_owner_endpoints_are_for_that_shops_owner_only(ready, buyer, owner, shop):
    oid = confirmed(ready, buyer)
    assert client.post(f"/owner/orders/{oid}/status", json={"to": "packing"}).status_code == 401
    # a customer token is not an owner token
    assert client.post(f"/owner/orders/{oid}/status", json={"to": "packing"}, headers=buyer["headers"]).status_code == 403
    # an owner of another shop
    from app.db import SessionLocal as S
    from app.models import Shop, Shopkeeper
    from app.security import create_access_token
    import uuid
    with S() as db:
        o2 = Shopkeeper(name="Other", email=f"x{uuid.uuid4().hex[:8]}@t.in", password_hash="x")
        db.add(o2)
        db.flush()
        s2 = Shop(owner_id=o2.id, name="Other", slug=f"o-{uuid.uuid4().hex[:8]}")
        db.add(s2)
        db.commit()
        o2id, s2id = o2.id, s2.id
    try:
        other = bearer(create_access_token(o2id, "shopkeeper"))
        assert move(other, oid, "packing").status_code == 403
        assert client.get(f"/owner/orders/{oid}", headers=other).status_code == 403
        assert client.get(f"/owner/orders/{oid}/delivery-note", headers=other).status_code == 403
        assert client.post(f"/orders/{oid}/cancel", json={"reason": "x"}, headers=other).status_code == 403
    finally:
        with S() as db:
            db.delete(db.get(Shop, s2id))
            db.delete(db.get(Shopkeeper, o2id))
            db.commit()
    assert move(owner, oid, "packing").status_code == 200  # the real owner still can


def test_the_system_moves_a_draft_between_open_states_and_records_them(mychat, monkeypatch):
    from tests.test_orchestrator import M, send
    order = send(mychat, M[1]).json()["order"]
    assert order["status"] == "needs_clarification"
    assert events(order["id"]) == [("draft", "needs_clarification", "system", None)]
    # no chat system message for these moves: the bot's own messages already narrate them
    assert not [m for m in conversation(mychat)["messages"] if m["sender"] == "system"]

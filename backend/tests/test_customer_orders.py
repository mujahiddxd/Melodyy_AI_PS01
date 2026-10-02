"""Customer login-gated order history, cart resume, and OCR failure handling."""
from app.agents import orchestrator
from app.llm.client import LLMError
from tests.order_helpers import (  # noqa: F401  (fixtures)
    bearer, buyer, client, confirm, conversation, mychat, owner, ready, say, shop,
)


def test_orders_requires_login():
    assert client.get("/customer/orders").status_code == 401


def test_open_order_is_cart_then_confirmed_is_past(ready, buyer):
    r = client.get("/customer/orders", headers=buyer["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert [o["id"] for o in body["cart"]] == [ready["id"]] and body["past"] == []
    row = body["cart"][0]
    assert row["is_cart"] and row["item_count"] == 2 and row["shop_slug"] == ready["chat"]["shop"]["slug"]

    # logging in again on a "new device" resumes the same conversation instead of starting an empty one
    again = client.post(f"/shops/{row['shop_slug']}/conversations", headers=buyer["headers"]).json()
    assert again["conversation"]["id"] == ready["chat"]["id"] and again["order"]["id"] == ready["id"]

    assert confirm(ready["id"], buyer["near"], buyer["headers"]).status_code == 200
    body = client.get("/customer/orders", headers=buyer["headers"]).json()
    assert body["cart"] == [] and [o["id"] for o in body["past"]] == [ready["id"]]
    assert body["past"][0]["status"] == "confirmed" and body["past"][0]["total"] != "0.00"


def test_orders_are_private(ready, buyer):
    from datetime import datetime, timezone
    import uuid
    from app.db import SessionLocal
    from app.models import Customer
    from app.security import create_access_token
    with SessionLocal() as db:
        other = Customer(phone=f"8{uuid.uuid4().int % 10**9:09d}", verified_at=datetime.now(timezone.utc))
        db.add(other)
        db.commit()
        oid = other.id
    try:
        body = client.get("/customer/orders", headers=bearer(create_access_token(oid, "customer"))).json()
        assert body == {"cart": [], "past": []}
    finally:
        with SessionLocal() as db:
            db.delete(db.get(Customer, oid))
            db.commit()


def test_ocr_failure_is_a_friendly_502_not_a_crash(mychat, monkeypatch):
    def boom(*a, **k):
        raise LLMError("vision down")
    monkeypatch.setattr(orchestrator, "run_ocr", boom)
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 32
    r = client.post(f"/conversations/{mychat['id']}/messages/image", headers=mychat["headers"],
                    files={"file": ("l.png", png, "image/png")})
    assert r.status_code == 502 and r.json()["detail"]["code"] == "LLM_FAILED", r.text

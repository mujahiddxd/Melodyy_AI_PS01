"""Shared fixtures for the Stage 4 tests: a verified customer with two addresses, a ready (billed) order, owner token.

The shop is the throw-away one from test_orchestrator (seed catalog, pin at 18.5 / 73.8, radius 3 km).
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import delete, select, update

from app.db import SessionLocal
from app.models import Conversation, Customer, CustomerAddress, Order, Product, Shop
from app.security import create_access_token
from tests.test_conversation_state import item, say  # noqa: F401
from tests.test_orchestrator import client, mock_llm, shop  # noqa: F401  (fixtures)

NEAR = (18.505, 73.805)  # about 0.7 km from the shop
FAR = (18.60, 73.80)     # about 11 km


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def buyer(shop):
    """A verified customer + one in-radius and one out-of-radius saved address."""
    with SessionLocal() as db:
        c = Customer(phone=f"9{uuid.uuid4().int % 10**9:09d}", verified_at=datetime.now(timezone.utc))
        db.add(c)
        db.flush()
        near = CustomerAddress(customer_id=c.id, label="Home", address_text="Flat 12, near the shop", lat=NEAR[0], lng=NEAR[1])
        far = CustomerAddress(customer_id=c.id, label="Other", address_text="Far away", lat=FAR[0], lng=FAR[1])
        db.add_all([near, far])
        db.commit()
        out = {"id": c.id, "phone": c.phone, "near": near.id, "far": far.id}
    out["headers"] = bearer(create_access_token(out["id"], "customer"))
    yield out
    with SessionLocal() as db:  # the shop fixture deletes the orders and conversations afterwards
        db.execute(update(Order).where(Order.customer_id == out["id"]).values(customer_id=None, address_id=None))
        db.execute(update(Conversation).where(Conversation.customer_id == out["id"]).values(customer_id=None))
        db.execute(delete(CustomerAddress).where(CustomerAddress.customer_id == out["id"]))
        db.execute(delete(Customer).where(Customer.id == out["id"]))
        db.commit()


@pytest.fixture
def owner(shop):
    return bearer(create_access_token(shop["owner_id"], "shopkeeper"))


@pytest.fixture
def mychat(shop, buyer):
    """A conversation that belongs to the verified customer (no guest token)."""
    r = client.post(f"/shops/{shop['slug']}/conversations", headers=buyer["headers"])
    assert r.status_code == 201, r.text
    return {"id": r.json()["conversation"]["id"], "headers": buyer["headers"], "shop": shop}


ATTA = item("2 kilo atta", "atta", "2", "kilo")
SUGAR = item("half kilo sugar", "sugar", "half", "kilo")


@pytest.fixture
def ready(mychat, monkeypatch):
    """Atta 2 kg + sugar 0.5 kg, nothing open: the order is awaiting_confirmation and the bill has been posted."""
    body = say(mychat, monkeypatch, "2 kilo atta aur half kilo sugar", [ATTA, SUGAR], intent="new_order")
    order = body["order"]
    assert order["status"] == "awaiting_confirmation", order["status"]
    return {"chat": mychat, "order": order, "id": order["id"], "body": body, "mp": monkeypatch}


def product(shop_id: int, name: str) -> Product:
    with SessionLocal() as db:
        return db.scalar(select(Product).where(Product.shop_id == shop_id, Product.name == name))


def stock(shop_id: int, name: str) -> Decimal:
    return product(shop_id, name).stock_qty


def set_product(shop_id: int, name: str, **values) -> None:
    with SessionLocal() as db:
        db.execute(update(Product).where(Product.shop_id == shop_id, Product.name == name).values(**values))
        db.commit()


def set_shop(shop_id: int, **values) -> None:
    with SessionLocal() as db:
        db.execute(update(Shop).where(Shop.id == shop_id).values(**values))
        db.commit()


def confirm(order_id: int, address_id: int, headers: dict, **extra):
    return client.post(f"/orders/{order_id}/confirm", json={"address_id": address_id, "payment_method": "cod", **extra},
                       headers=headers)


def conversation(chat) -> dict:
    return client.get(f"/conversations/{chat['id']}", headers=chat["headers"]).json()

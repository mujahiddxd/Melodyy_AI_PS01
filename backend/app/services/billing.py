"""Deterministic billing. Prices come ONLY from `products` (current DB rows); everything is Decimal, 2 places.

`quote_order` snapshots the current price on every billable line (`unit_price_snapshot`, `line_total`) and the order
totals. The confirm step later compares the live price with that snapshot, so a price edited between the quote and
the confirm is caught (409 PRICE_CHANGED) instead of being charged silently.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Order, OrderItem, Product, Shop
from app.services import orders as orders_svc

CENT = Decimal("0.01")


def money(v: Decimal) -> Decimal:
    return v.quantize(CENT, rounding=ROUND_HALF_UP)


def is_billable(item: OrderItem) -> bool:
    """Lines that are part of the bill (and of the stock deduction): settled, with a product and a quantity."""
    return (
        item.status == "matched" and item.product_id is not None
        and item.product_qty is not None and item.product_qty > 0
    )


def billable_items(db: Session, order: Order) -> list[OrderItem]:
    return [i for i in orders_svc.order_items(db, order.id) if is_billable(i)]


def _products(db: Session, ids: set[int]) -> dict[int, Product]:
    return {p.id: p for p in db.scalars(select(Product).where(Product.id.in_(ids)))} if ids else {}


def line_dict(item: OrderItem, product: Product) -> dict:
    """One bill line, display facts taken from the product row. Money as 2-decimal strings."""
    loose = product.sell_mode == "loose"
    return {
        "item_id": item.id,
        "product_id": product.id,
        "name": product.name,
        "qty": f"{item.product_qty:.3f}",
        "unit": product.pack_unit if loose else "pack",
        "qty_label": orders_svc.qty_text(product, item.product_qty),
        "unit_price": f"{item.unit_price_snapshot:.2f}",
        "line_total": f"{item.line_total:.2f}",
    }


def bill_dict(db: Session, order: Order) -> dict:
    """The bill as stored on the order (what the customer was shown). Lines come from the snapshot columns."""
    items = [i for i in billable_items(db, order) if i.unit_price_snapshot is not None]
    products = _products(db, {i.product_id for i in items})
    return {
        "order_id": order.id,
        "order_no": 1000 + order.id,
        "lines": [line_dict(i, products[i.product_id]) for i in items],
        "subtotal": f"{order.subtotal:.2f}",
        "discount": f"{order.discount:.2f}",
        "delivery_fee": f"{order.delivery_fee:.2f}",
        "total": f"{order.total:.2f}",
        "payment_method": order.payment_method,
        "requires_reapproval": order.requires_reapproval,
        "quoted_at": order.quoted_at.isoformat() if order.quoted_at else None,
    }


def quote_order(db: Session, order: Order, shop: Shop) -> dict:
    """Recompute the bill from CURRENT prices and save it on the order. Flushes, does not commit. Returns the bill."""
    items = billable_items(db, order)
    products = _products(db, {i.product_id for i in items})
    subtotal = Decimal(0)
    for item in items:
        price = products[item.product_id].price
        item.unit_price_snapshot = money(price)
        item.line_total = money(price * item.product_qty)
        subtotal += item.line_total
    order.subtotal = money(subtotal)
    order.delivery_fee = money(shop.delivery_fee) if items else Decimal("0.00")
    order.total = money(order.subtotal - order.discount + order.delivery_fee)
    order.quoted_at = datetime.now(timezone.utc)
    db.flush()
    return bill_dict(db, order)


def price_changes(db: Session, order: Order) -> list[dict]:
    """Billable lines whose live price differs from the quoted snapshot (an unquoted line counts as changed)."""
    items = billable_items(db, order)
    products = _products(db, {i.product_id for i in items})
    out = []
    for i in items:
        now = money(products[i.product_id].price)
        if i.unit_price_snapshot is None or now != i.unit_price_snapshot:
            out.append({
                "item_id": i.id, "product_name": products[i.product_id].name,
                "old_price": None if i.unit_price_snapshot is None else f"{i.unit_price_snapshot:.2f}",
                "new_price": f"{now:.2f}",
            })
    return out

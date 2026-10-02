"""Order actions that change inventory or money: confirm, cancel, shopkeeper status moves.

Rules (plan section 0 and Stage 4):
  * Inventory is deducted ONLY inside `confirm_order`, in one transaction, after `SELECT ... FOR UPDATE` on the order
    and on every product line (in id order, so two orders can never deadlock each other).
  * Stock and price are checked again under those locks. A problem rolls the whole transaction back; the follow-up
    (mark the line out of stock + clarification, or re-quote) is written in a fresh transaction, then the 409 is raised.
  * Confirming twice is harmless: the second request waits on the order lock, sees `confirmed` and returns it.
  * Cancelling an order whose stock was deducted puts exactly that stock back, once.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.base import RunCtx
from app.agents.billing import run_billing
from app.agents.types import option_dict
from app.errors import api_error
from app.models import Clarification, Conversation, Customer, CustomerAddress, Message, Order, Product, Shop
from app.schemas.conversation import MessageOut
from app.services import billing as billing_svc
from app.services import geo
from app.services import language as lang_svc
from app.services import order_state_machine as osm
from app.services import orders as orders_svc
from app.services.inventory import alternatives

D = Decimal
BEYOND_CONFIRMED = ("confirmed", "packing", "out_for_delivery", "delivered")


def lock_order(db: Session, order_id: int) -> Order:
    """The order row, locked until this transaction ends (404 when it does not exist).

    FOR NO KEY UPDATE, not FOR UPDATE: still exclusive between two confirms, but it does not block the agent_runs
    rows that agents write from their own sessions (their foreign key to the order takes a key-share lock)."""
    order = db.scalar(
        select(Order).where(Order.id == order_id).with_for_update(key_share=True)
        .execution_options(populate_existing=True)
    )
    if order is None:
        raise api_error(404, "NOT_FOUND", "Order not found.")
    return order


def _lang_of(db: Session, order: Order) -> str:
    conv = db.get(Conversation, order.conversation_id)
    return lang_svc.reply_lang(conv.language, conv.script) if conv else "hinglish"


def _lock_products(db: Session, ids: set[int]) -> dict[int, Product]:
    if not ids:
        return {}
    rows = db.scalars(
        select(Product).where(Product.id.in_(sorted(ids))).order_by(Product.id).with_for_update()
        .execution_options(populate_existing=True)
    )
    return {p.id: p for p in rows}


def _needed(items) -> dict[int, Decimal]:
    need: dict[int, Decimal] = defaultdict(D)
    for i in items:
        need[i.product_id] += i.product_qty
    return need


def _fail_body(db: Session, order: Order, messages: list[Message]) -> dict:
    return {
        "messages": [MessageOut.model_validate(m).model_dump(mode="json") for m in messages],
        "order": orders_svc.serialize_order(db, order).model_dump(mode="json"),
    }


# ---- confirm ---------------------------------------------------------------------------------------------
def confirm_order(
    db: Session, order_id: int, customer: Customer, address_id: int, payment_method: str,
) -> tuple[Order, bool]:
    """Returns (order, newly_confirmed). Raises coded HTTP errors; see API_CONTRACT.md section 6."""
    order = lock_order(db, order_id)
    conv = db.get(Conversation, order.conversation_id)
    if conv is None or conv.customer_id != customer.id:
        db.rollback()
        raise api_error(403, "FORBIDDEN", "This order belongs to someone else.")

    if order.status in BEYOND_CONFIRMED:  # idempotent: already confirmed (or further): nothing is deducted again
        db.rollback()
        return order, False

    # 1. state machine + no open questions
    if order.status in osm.OPEN_STATES and orders_svc.open_clarifications(db, order.id):
        db.rollback()
        raise api_error(409, "OPEN_CLARIFICATIONS", "Please answer the open questions before confirming.")
    if not osm.can_transition(order.status, "confirmed", "customer"):
        frm = order.status
        db.rollback()
        raise osm.invalid_transition(frm, "confirmed")
    items = billing_svc.billable_items(db, order)
    if not items:
        db.rollback()
        raise api_error(422, "VALIDATION_ERROR", "There is nothing in this order to confirm.")

    # 2. delivery address, re-checked on the server
    addr = db.get(CustomerAddress, address_id)
    if addr is None or addr.customer_id != customer.id:
        db.rollback()
        raise api_error(404, "NOT_FOUND", "Delivery address not found.")
    shop = db.get(Shop, order.shop_id)
    shop_name = shop.name
    try:
        check = geo.check_delivery(shop, addr.lat, addr.lng)
    except geo.ShopLocationNotSet:
        db.rollback()
        raise api_error(422, "SHOP_LOCATION_NOT_SET", f"{shop_name} hasn't set its delivery area yet.")
    if not check.eligible:
        db.rollback()
        raise api_error(
            422, "OUT_OF_RADIUS",
            f"Sorry, {shop_name} delivers within {check.radius_km:g} km. This address is {check.distance_km:.2f} km away.",
            distance_km=round(check.distance_km, 2), radius_km=check.radius_km,
        )

    # 3. one transaction: lock the products, re-check stock and price, deduct
    need = _needed(items)
    products = _lock_products(db, set(need))
    short = [i for i in items if not products[i.product_id].is_active or products[i.product_id].stock_qty < need[i.product_id]]
    if short:
        _stock_changed(db, order.id, [i.id for i in short])  # rolls back, writes the follow-up, raises 409
    changes = billing_svc.price_changes(db, order)
    if changes:
        _price_changed(db, order.id, changes)  # rolls back, re-quotes, raises 409

    for pid, qty in need.items():
        products[pid].stock_qty = products[pid].stock_qty - qty
    order.address_id = addr.id
    order.delivery_address_text = addr.address_text
    order.delivery_lat, order.delivery_lng = addr.lat, addr.lng
    order.distance_km = D(str(round(check.distance_km, 2)))
    order.payment_method, order.payment_status = payment_method, "cod"
    order.requires_reapproval = False
    lang = lang_svc.reply_lang(conv.language, conv.script)
    text = f"{lang_svc.STATUS_MESSAGES['confirmed'][lang].format(no=1000 + order.id)} Total ₹{order.total:.2f} · COD"
    osm.transition(db, order, "confirmed", "customer", text=text, kind="order_confirmed")
    db.commit()
    return order, True


def _stock_changed(db: Session, order_id: int, item_ids: list[int]) -> None:
    """Stock is short for these lines: nothing was deducted. Mark them out of stock, ask the customer (with in-stock
    alternatives from the database), and report 409 STOCK_CHANGED."""
    db.rollback()
    order = lock_order(db, order_id)
    conv = db.get(Conversation, order.conversation_id)
    lang = lang_svc.reply_lang(conv.language, conv.script)
    catalog = orders_svc.load_catalog(db, order.shop_id)
    by_id = {i.id: i for i in orders_svc.order_items(db, order.id)}
    products = {p.id: p for p in db.scalars(select(Product).where(Product.id.in_({by_id[i].product_id for i in item_ids})))}
    reported, questions = [], []
    for iid in item_ids:
        item = by_id[iid]
        product = products[item.product_id]
        available = max(product.stock_qty, D(0))
        options = [option_dict(p) for p in alternatives(product, catalog)]
        item.status = "out_of_stock"
        question = lang_svc.item_question(
            lang, item.name_guess, "out_of_stock", product.name, [{"name": o["label"]} for o in options],
            f"{available.normalize():f}",
        )
        db.add(Clarification(order_id=order.id, order_item_id=item.id, kind="out_of_stock", question=question, options=options))
        questions.append(question)
        reported.append({"item_id": item.id, "product_name": product.name, "available_qty": f"{available:.3f}"})
    db.flush()
    if order.status == "awaiting_confirmation":
        osm.transition(db, order, "needs_clarification", "system")
    open_ids = [c.id for c in orders_svc.open_clarifications(db, order.id)]
    bot = Message(
        conversation_id=order.conversation_id, sender="bot", type="text", content="\n".join(questions),
        meta={"reason": "stock_changed", "order_id": order.id, "clarification_ids": open_ids},
    )
    db.add(bot)
    db.flush()
    body = _fail_body(db, order, [bot])
    db.commit()
    names = ", ".join(dict.fromkeys(r["product_name"] for r in reported))
    raise api_error(409, "STOCK_CHANGED", f"Stock changed for {names}, please review.", items=reported, **body)


def _price_changed(db: Session, order_id: int, changes: list[dict]) -> None:
    """A price moved since the quote: nothing was deducted. Re-quote from current prices, flag the order for
    re-approval, post the new bill, and report 409 PRICE_CHANGED."""
    db.rollback()
    order = lock_order(db, order_id)
    shop = db.get(Shop, order.shop_id)
    old_total = f"{order.total:.2f}"
    order.requires_reapproval = True
    ctx = RunCtx(db=db, conversation_id=order.conversation_id, order_id=order.id)
    bill_msg = run_billing(ctx, order, shop, reason="price_changed")
    body = _fail_body(db, order, [bill_msg])
    new_total = f"{order.total:.2f}"
    db.commit()
    names = ", ".join(dict.fromkeys(c["product_name"] for c in changes))
    raise api_error(
        409, "PRICE_CHANGED", f"Price changed for {names}.", changes=changes, old_total=old_total, new_total=new_total,
        **body,
    )


# ---- cancel / shopkeeper status ---------------------------------------------------------------------------
def cancel_order(db: Session, order_id: int, actor: str, reason: str | None) -> Order:
    """Cancel before delivery. Stock that confirm deducted is restored in the same transaction. Idempotent."""
    order = lock_order(db, order_id)
    if order.status == "cancelled":
        db.rollback()
        return order
    if not osm.can_transition(order.status, "cancelled", actor):
        frm = order.status
        db.rollback()
        raise osm.invalid_transition(frm, "cancelled")
    if order.status in osm.STOCK_HELD_STATES:
        items = billing_svc.billable_items(db, order)
        need = _needed(items)
        for pid, p in _lock_products(db, set(need)).items():
            p.stock_qty = p.stock_qty + need[pid]
    osm.transition(db, order, "cancelled", actor, note=reason)
    db.commit()
    return order


def owner_set_status(db: Session, order_id: int, to: str, note: str | None) -> Order:
    """Shopkeeper moves: confirmed -> packing -> out_for_delivery -> delivered (cancel goes through cancel_order)."""
    if to == "cancelled":
        return cancel_order(db, order_id, "shopkeeper", note)
    order = lock_order(db, order_id)
    frm = order.status
    if not osm.can_transition(frm, to, "shopkeeper"):
        db.rollback()
        raise osm.invalid_transition(frm, to)
    osm.transition(db, order, to, "shopkeeper", note=note)
    db.commit()
    return order

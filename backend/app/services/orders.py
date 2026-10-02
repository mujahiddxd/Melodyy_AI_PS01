"""Order persistence and serialization for the chat flow. Prices and stock only ever come from `products`."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.agents.types import ItemPlan, option_dict
from app.models import AgentRun, Clarification, Conversation, Message, Order, OrderItem, Product
from app.models.conversation import OPEN_ORDER_STATUSES
from app.schemas.conversation import (
    AgentRunOut, ClarificationOut, MessageOut, OrderItemOut, OrderOut, ProductSummary,
)
from app.services.language import item_question
from app.services.matcher import norm
from app.services.unit_normalizer import canonical_qty

OPEN_CLARIFICATION = Clarification.resolved_at.is_(None)


def load_catalog(db: Session, shop_id: int) -> list[Product]:
    return list(db.scalars(
        select(Product).where(Product.shop_id == shop_id, Product.is_active.is_(True)).order_by(Product.id)
    ))


def active_order(db: Session, conversation_id: int) -> Order | None:
    return db.scalar(
        select(Order)
        .where(Order.conversation_id == conversation_id, Order.status.in_(OPEN_ORDER_STATUSES))
        .order_by(Order.id.desc())
    )


def latest_order(db: Session, conversation_id: int) -> Order | None:
    return active_order(db, conversation_id) or db.scalar(
        select(Order).where(Order.conversation_id == conversation_id).order_by(Order.id.desc())
    )


def create_order(db: Session, conv: Conversation) -> Order:
    order = Order(shop_id=conv.shop_id, customer_id=conv.customer_id, conversation_id=conv.id, status="draft")
    db.add(order)
    db.flush()
    return order


def open_clarifications(db: Session, order_id: int) -> list[Clarification]:
    return list(db.scalars(
        select(Clarification).where(Clarification.order_id == order_id, OPEN_CLARIFICATION).order_by(Clarification.id)
    ))


def order_items(db: Session, order_id: int) -> list[OrderItem]:
    return list(db.scalars(select(OrderItem).where(OrderItem.order_id == order_id).order_by(OrderItem.id)))


def _conf(v: float) -> Decimal:
    return Decimal(str(min(max(v, 0.0), 1.0))).quantize(Decimal("0.01"))


def apply_plan_to_item(item: OrderItem, plan: ItemPlan) -> None:
    """Write the resolved state of a plan onto an order line."""
    item.product_id = plan.product.id if plan.product else None
    item.quantity_value = plan.qty.value
    item.unit = plan.qty.unit
    item.normalized_qty = plan.normalized_qty if plan.normalized_qty is not None else canonical_qty(plan.qty)
    item.product_qty = plan.product_qty
    item.confidence = _conf(plan.confidence)
    item.status = plan.status
    item.candidates = plan.candidates


def open_clarification_for(db: Session, order: Order, item: OrderItem, plan: ItemPlan, lang: str) -> Clarification:
    options = [option_dict(p) for p in plan.options]
    question = item_question(
        lang, plan.word, plan.kind or "unmatched", plan.product.name if plan.product else None,
        [{"name": o["label"]} for o in options], None if plan.available is None else f"{plan.available.normalize():f}",
    )
    clar = Clarification(order_id=order.id, order_item_id=item.id, kind=plan.kind, question=question, options=options)
    db.add(clar)
    db.flush()
    return clar


def _plan_key(plan: ItemPlan) -> tuple:
    if plan.product is not None:
        return ("p", plan.product.id)
    if plan.status == "ambiguous":
        return ("c", frozenset(p.id for p in plan.options))
    return ("n", norm(plan.word))


def _item_key(item: OrderItem) -> tuple:
    if item.product_id:
        return ("p", item.product_id)
    if item.status == "ambiguous":
        return ("c", frozenset(c["product_id"] for c in (item.candidates or [])))
    return ("n", norm(item.name_guess))


def supersede_unresolved(db: Session, order: Order, plan: ItemPlan) -> list[int]:
    """The customer said it again: an unresolved line (open question) for the same product is replaced by the new
    line instead of leaving two questions about one thing. Same product, same candidate set, same unknown word, or
    the new product is one of the options we offered for the old line ("Mother Dairy Butter 100g" after the Amul
    butter was out of stock). Resolved lines are never touched. Returns the ids of the replaced items."""
    new_key = _plan_key(plan)
    replaced: list[int] = []
    items = {i.id: i for i in order_items(db, order.id)}
    for clar in open_clarifications(db, order.id):
        item = items.get(clar.order_item_id)
        if item is None or item.status == "removed":
            continue
        offered = {o["product_id"] for o in (clar.options or [])}
        old_key = _item_key(item)
        same = old_key == new_key
        picks_candidate = plan.product is not None and (
            plan.product.id in offered or (old_key[0] == "c" and plan.product.id in old_key[1])
        )
        if same or picks_candidate:
            item.status = "removed"
            item.product_qty = None
            clar.answer = {"superseded": True}
            clar.resolved_at = datetime.now(timezone.utc)
            replaced.append(item.id)
    if replaced:
        db.flush()  # autoflush is off
    return replaced


def save_plans(db: Session, order: Order, plans: list[ItemPlan], lang: str) -> list[Clarification]:
    """Insert the order lines (and one clarification per line that needs an answer). Flushes, does not commit.
    Returns only the clarifications opened by these plans."""
    created: list[Clarification] = []
    for plan in plans:
        supersede_unresolved(db, order, plan)
        item = OrderItem(
            order_id=order.id, raw_text=plan.parsed.raw_text or plan.word, name_guess=plan.word[:160],
            source_span=plan.parsed.source_span, status=plan.status,
        )
        apply_plan_to_item(item, plan)
        db.add(item)
        db.flush()
        if plan.kind:
            created.append(open_clarification_for(db, order, item, plan, lang))
    return created


def refresh_status(db: Session, order: Order) -> None:
    """needs_clarification while any clarification is open, else awaiting_confirmation (draft if nothing is left)."""
    if order.status not in OPEN_ORDER_STATUSES:
        return
    live = [i for i in order_items(db, order.id) if i.status != "removed"]
    if open_clarifications(db, order.id):
        order.status = "needs_clarification"
    elif live:
        order.status = "awaiting_confirmation"
    else:
        order.status = "draft"


def order_summary_text(db: Session, order: Order | None) -> str:
    """Compact summary of the current order for the parser prompt (names only: no prices, no ids)."""
    if order is None:
        return "empty"
    lines = []
    for i in order_items(db, order.id):
        if i.status == "removed":
            continue
        qty = "" if i.quantity_value is None else f" {i.quantity_value.normalize():f} {i.unit or ''}".rstrip()
        lines.append(f"{i.name_guess}{qty} ({i.status})")
    return "; ".join(lines) or "empty"


def qty_text(product: Product, product_qty: Decimal | None) -> str:
    """"x4" for packs, "0.5 kg" for loose items (what the customer gets, from the database row)."""
    if product_qty is None:
        return ""
    n = f"{product_qty.normalize():f}"
    if product.sell_mode == "pack":
        return f"×{n}"
    return f"{n} {UNIT_SHOWN.get(product.pack_unit, product.pack_unit)}"


UNIT_SHOWN = {"l": "L"}


def line_summary(db: Session, order: Order, products: dict[int, Product]) -> str:
    """"Atta (Loose) 2 kg, Parle-G 250g x4": the settled lines of the order."""
    parts = []
    for i in order_items(db, order.id):
        p = products.get(i.product_id) if i.product_id else None
        if i.status == "matched" and p is not None:
            parts.append(f"{p.name} {qty_text(p, i.product_qty)}".strip())
    return ", ".join(parts)


def price_text(option: dict) -> str:
    """"₹155" for a pack, "₹110 per kg" for loose items: the only prices the clarifier may repeat."""
    amount = f"{Decimal(option['price']).normalize():f}"
    per = option["pack"] if option["pack"].startswith("per ") else ""
    return f"₹{amount} {per}".strip()


def clarification_facts(
    db: Session, order: Order, products: dict[int, Product], only_ids: set[int] | None = None,
) -> list[dict]:
    """What the clarifier LLM may talk about: open clarifications (optionally only `only_ids`, the ones raised by
    the latest message), options straight from the database."""
    items = {i.id: i for i in order_items(db, order.id)}
    facts = []
    for c in open_clarifications(db, order.id):
        if only_ids is not None and c.id not in only_ids:
            continue
        item = items[c.order_item_id]
        product = products.get(item.product_id) if item.product_id else None
        fact = {
            "customer_word": item.name_guess,
            "problem": c.kind,
            "options": [{"name": o["label"], "pack": o["pack"], "price": price_text(o)} for o in (c.options or [])],
        }
        if product is not None:
            fact["name"] = product.name
            if c.kind == "out_of_stock":
                fact["available"] = f"{max(product.stock_qty, Decimal(0)).normalize():f}"
        facts.append(fact)
    return facts


# ---- serialization --------------------------------------------------------------------------------------
def serialize_order(db: Session, order: Order | None) -> OrderOut | None:
    if order is None:
        return None
    items = order_items(db, order.id)
    pids = {i.product_id for i in items if i.product_id}
    products = {p.id: p for p in db.scalars(select(Product).where(Product.id.in_(pids)))} if pids else {}
    clars = list(db.scalars(select(Clarification).where(Clarification.order_id == order.id).order_by(Clarification.id)))
    out_items = []
    for i in items:
        p = products.get(i.product_id) if i.product_id else None
        out_items.append(OrderItemOut(
            id=i.id, product_id=i.product_id, product_name=p.name if p else None, raw_text=i.raw_text,
            name_guess=i.name_guess, quantity_value=i.quantity_value, unit=i.unit, normalized_qty=i.normalized_qty,
            product_qty=i.product_qty, unit_price_snapshot=i.unit_price_snapshot, line_total=i.line_total,
            confidence=float(i.confidence), status=i.status, candidates=i.candidates or [],
            source_span=i.source_span, product=ProductSummary.model_validate(p) if p else None,
        ))
    return OrderOut(
        id=order.id, order_no=1000 + order.id, shop_id=order.shop_id, conversation_id=order.conversation_id,
        status=order.status, requires_reapproval=order.requires_reapproval, items=out_items,
        clarifications=[ClarificationOut.model_validate(c) for c in clars],
        subtotal=order.subtotal, discount=order.discount, delivery_fee=order.delivery_fee, total=order.total,
        delivery_address_text=order.delivery_address_text, delivery_lat=order.delivery_lat,
        delivery_lng=order.delivery_lng, distance_km=float(order.distance_km) if order.distance_km is not None else None,
        requested_delivery_text=order.requested_delivery_text, requested_delivery_at=order.requested_delivery_at,
        payment_method=order.payment_method, payment_status=order.payment_status,
        quoted_at=order.quoted_at, confirmed_at=order.confirmed_at, created_at=order.created_at,
    )


def latest_agent_runs(db: Session, conversation_id: int) -> list[AgentRun]:
    """The runs of the most recent message that has any."""
    last = db.scalar(
        select(AgentRun.message_id).where(AgentRun.conversation_id == conversation_id, AgentRun.message_id.is_not(None))
        .order_by(AgentRun.id.desc()).limit(1)
    )
    if last is None:
        return []
    return list(db.scalars(
        select(AgentRun).where(AgentRun.conversation_id == conversation_id, AgentRun.message_id == last)
        .order_by(AgentRun.id)
    ))


def link_runs_to_order(db: Session, run_ids: list[int], order_id: int) -> None:
    """Runs are written before the order is committed, so they are linked afterwards."""
    if run_ids:
        db.execute(update(AgentRun).where(AgentRun.id.in_(run_ids)).values(order_id=order_id))


def messages_out(msgs: list[Message]) -> list[MessageOut]:
    return [MessageOut.model_validate(m) for m in msgs]


def runs_out(runs: list[AgentRun]) -> list[AgentRunOut]:
    return [AgentRunOut.model_validate(r) for r in runs]

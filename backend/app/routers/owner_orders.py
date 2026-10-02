"""Shopkeeper order board: list, detail, status moves, delivery note. See API_CONTRACT.md section 6."""
from collections import defaultdict

from fastapi import APIRouter, Depends, Query
from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_owner_shop
from app.errors import api_error
from app.models import AgentRun, Clarification, Customer, Message, Order, OrderItem, Shop
from app.models.conversation import ORDER_STATUSES
from app.schemas.conversation import AgentRunOut, MessageOut
from app.schemas.order import (
    DeliveryNote, DeliveryNoteItem, OrderEnvelope, OwnerCustomer, OwnerOrderCard, OwnerOrderDetail, OwnerOrderList,
    OwnerShopPin, StatusIn,
)
from app.routers.orders import timeline_of
from app.services import billing as billing_svc
from app.services import order_actions
from app.services import order_state_machine as osm
from app.services import orders as orders_svc

router = APIRouter(prefix="/owner/orders", tags=["owner orders"])
BOARD_LIMIT = 200


def mask_phone(phone: str | None) -> str | None:
    """"9876543210" -> "98****3210"."""
    if not phone:
        return None
    return f"{phone[:2]}****{phone[-4:]}" if len(phone) > 6 else "*" * len(phone)


def _own_order(db: Session, shop: Shop, order_id: int) -> Order:
    order = db.get(Order, order_id)
    if order is None:
        raise api_error(404, "NOT_FOUND", "Order not found.")
    if order.shop_id != shop.id:
        raise api_error(403, "FORBIDDEN", "This order belongs to another shop.")
    return order


def _problems(db: Session, order: Order) -> list[str]:
    """Why this order needs the shopkeeper's attention (shown as a red dot on the card, listed in the drawer)."""
    out = []
    items = orders_svc.order_items(db, order.id)
    if order.requires_reapproval:
        out.append("Price changed: the customer must approve the new bill.")
    if any(i.status == "out_of_stock" for i in items):
        out.append("A line is out of stock.")
    if order.status == "needs_clarification" and orders_svc.open_clarifications(db, order.id):
        out.append("Waiting for the customer to answer a question.")
    return out


@router.get("", response_model=OwnerOrderList)
def list_orders(
    status: str | None = Query(default=None),
    q: str = Query(default="", max_length=100),
    shop: Shop = Depends(get_owner_shop),
    db: Session = Depends(get_db),
):
    if status is not None and status not in ORDER_STATUSES:
        raise api_error(422, "VALIDATION_ERROR", f"Unknown status '{status}'.")
    stmt = select(Order, Customer.phone).join(Customer, Customer.id == Order.customer_id, isouter=True)
    stmt = stmt.where(Order.shop_id == shop.id)
    if status:
        stmt = stmt.where(Order.status == status)
    else:  # the board: drafts have no bill yet, cancelled orders are a filter of their own
        stmt = stmt.where(Order.status.notin_(["draft", "cancelled"]))
    term = q.strip().lstrip("#")
    if term:
        conds = [Customer.phone.ilike(f"%{term}%")]
        if term.isdigit() and int(term) > 1000:
            conds.append(Order.id == int(term) - 1000)
        like = f"%{term}%"
        conds.append(exists().where(
            OrderItem.order_id == Order.id, or_(OrderItem.name_guess.ilike(like), OrderItem.raw_text.ilike(like)),
        ))
        stmt = stmt.where(or_(*conds))
    rows = db.execute(stmt.order_by(Order.updated_at.desc(), Order.id.desc()).limit(BOARD_LIMIT)).all()

    ids = [o.id for o, _ in rows]
    counts: dict[int, int] = defaultdict(int)
    bad_items: set[int] = set()
    open_clar: set[int] = set()
    if ids:
        for oid, n in db.execute(
            select(OrderItem.order_id, func.count()).where(OrderItem.order_id.in_(ids), OrderItem.status != "removed")
            .group_by(OrderItem.order_id)
        ):
            counts[oid] = n
        bad_items = set(db.scalars(
            select(OrderItem.order_id).where(OrderItem.order_id.in_(ids), OrderItem.status == "out_of_stock")
        ))
        open_clar = set(db.scalars(
            select(Clarification.order_id).where(Clarification.order_id.in_(ids), Clarification.resolved_at.is_(None))
        ))
    cards = [
        OwnerOrderCard(
            id=o.id, order_no=1000 + o.id, status=o.status, customer_phone_masked=mask_phone(phone),
            item_count=counts[o.id], total=o.total, payment_method=o.payment_method, payment_status=o.payment_status,
            requested_delivery_text=o.requested_delivery_text, requested_delivery_at=o.requested_delivery_at,
            has_problem=o.requires_reapproval or o.id in bad_items or (o.status == "needs_clarification" and o.id in open_clar),
            created_at=o.created_at, updated_at=o.updated_at,
        )
        for o, phone in rows
    ]
    return OwnerOrderList(items=cards)


@router.get("/{order_id}", response_model=OwnerOrderDetail)
def order_detail(order_id: int, shop: Shop = Depends(get_owner_shop), db: Session = Depends(get_db)):
    order = _own_order(db, shop, order_id)
    customer = db.get(Customer, order.customer_id) if order.customer_id else None
    runs = list(db.scalars(select(AgentRun).where(AgentRun.order_id == order.id).order_by(AgentRun.id).limit(200)))
    message_ids = {r.message_id for r in runs if r.message_id}
    originals = list(db.scalars(
        select(Message).where(Message.id.in_(message_ids), Message.sender == "customer").order_by(Message.id)
    )) if message_ids else []
    quoted = order.quoted_at is not None
    return OwnerOrderDetail(
        order=orders_svc.serialize_order(db, order),
        customer=OwnerCustomer(phone_masked=mask_phone(customer.phone if customer else None)),
        shop=OwnerShopPin(name=shop.name, lat=shop.lat, lng=shop.lng),
        messages=[MessageOut.model_validate(m) for m in originals],
        bill=billing_svc.bill_dict(db, order) if quoted else None,
        problems=_problems(db, order),
        allowed_next=osm.allowed_next(order.status, "shopkeeper"),
        timeline=timeline_of(db, order.id),
        agent_runs=[AgentRunOut.model_validate(r) for r in runs],
    )


@router.post("/{order_id}/status", response_model=OrderEnvelope)
def set_status(order_id: int, body: StatusIn, shop: Shop = Depends(get_owner_shop), db: Session = Depends(get_db)):
    _own_order(db, shop, order_id)
    note = (body.note or "").strip() or None
    if body.to == "cancelled" and not note:
        raise api_error(422, "VALIDATION_ERROR", "Please give a reason for cancelling this order.")
    order = order_actions.owner_set_status(db, order_id, body.to, note)
    return OrderEnvelope(order=orders_svc.serialize_order(db, order))


@router.get("/{order_id}/delivery-note", response_model=DeliveryNote)
def delivery_note(order_id: int, shop: Shop = Depends(get_owner_shop), db: Session = Depends(get_db)):
    order = _own_order(db, shop, order_id)
    customer = db.get(Customer, order.customer_id) if order.customer_id else None
    bill = billing_svc.bill_dict(db, order)
    return DeliveryNote(
        order_no=1000 + order.id, shop_name=shop.name, customer_phone=customer.phone if customer else None,
        delivery_address_text=order.delivery_address_text, delivery_lat=order.delivery_lat,
        delivery_lng=order.delivery_lng, requested_delivery_text=order.requested_delivery_text,
        requested_delivery_at=order.requested_delivery_at,
        items=[DeliveryNoteItem(**{k: ln[k] for k in DeliveryNoteItem.model_fields}) for ln in bill["lines"]],
        subtotal=bill["subtotal"], delivery_fee=bill["delivery_fee"], total=bill["total"],
        payment_method=order.payment_method, payment_status=order.payment_status, created_at=order.created_at,
    )

"""Customer-side order endpoints: quote, confirm, cancel, read. See API_CONTRACT.md section 6."""
from fastapi import APIRouter, Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.base import RunCtx
from app.agents.billing import run_billing
from app.db import get_db
from app.deps import find_owner_shop, get_current_customer, hash_guest_session
from app.errors import api_error
from app.models import Conversation, Customer, Order, OrderStatusEvent, Shop, Shopkeeper
from app.schemas.conversation import MessageOut
from app.schemas.order import (
    CancelIn, ConfirmIn, ConfirmOut, CustomerOrderOut, OrderEnvelope, QuoteOut, StatusEventOut,
)
from app.security import decode_token
from app.services import billing as billing_svc
from app.services import order_actions
from app.services import order_state_machine as osm
from app.services import orders as orders_svc

router = APIRouter(prefix="/orders", tags=["orders"])
_bearer = HTTPBearer(auto_error=False)


def _unauthorized():
    exc = api_error(401, "UNAUTHORIZED", "Please log in again.")
    exc.headers = {"WWW-Authenticate": "Bearer"}
    return exc


def _get_order(db: Session, order_id: int) -> Order:
    order = db.get(Order, order_id)
    if order is None:
        raise api_error(404, "NOT_FOUND", "Order not found.")
    return order


def resolve_actor(
    order_id: int,
    db: Session = Depends(get_db),
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    x_guest_session: str | None = Header(default=None),
) -> tuple[Order, str]:
    """Who is calling, and may they touch this order? (order, "customer" | "shopkeeper").

    Owner Bearer: the order must belong to the owner's shop. Customer Bearer: the order's conversation must belong to
    that customer. Otherwise the guest session of the order's conversation. 401 without any credential; 403 for
    somebody else's order."""
    claims = decode_token(creds.credentials) if creds else None
    if claims and str(claims.get("sub", "")).isdigit():
        if claims.get("role") == "shopkeeper":
            owner = db.get(Shopkeeper, int(claims["sub"]))
            shop = find_owner_shop(db, owner) if owner else None
            if shop is None:
                raise _unauthorized()
            order = _get_order(db, order_id)
            if order.shop_id != shop.id:
                raise api_error(403, "FORBIDDEN", "This order belongs to another shop.")
            return order, "shopkeeper"
        if claims.get("role") == "customer":
            customer = db.get(Customer, int(claims["sub"]))
            if customer is not None and customer.verified_at is not None:
                order = _get_order(db, order_id)
                conv = db.get(Conversation, order.conversation_id)
                if conv is not None and conv.customer_id == customer.id:
                    return order, "customer"
                if not x_guest_session:
                    raise api_error(403, "FORBIDDEN", "This order belongs to someone else.")
    if not x_guest_session:
        raise _unauthorized()
    order = _get_order(db, order_id)
    conv = db.get(Conversation, order.conversation_id)
    if conv is None or conv.guest_session_id != hash_guest_session(x_guest_session):
        raise api_error(403, "FORBIDDEN", "This order belongs to someone else.")
    return order, "customer"


def _customer_only(actor: tuple[Order, str]) -> Order:
    order, who = actor
    if who != "customer":
        raise api_error(403, "FORBIDDEN", "This action is for the customer who placed the order.")
    return order


def timeline_of(db: Session, order_id: int) -> list[StatusEventOut]:
    rows = db.scalars(
        select(OrderStatusEvent).where(OrderStatusEvent.order_id == order_id).order_by(OrderStatusEvent.id)
    )
    return [StatusEventOut.model_validate(r) for r in rows]


@router.post("/{order_id}/quote", response_model=QuoteOut)
def quote(actor: tuple[Order, str] = Depends(resolve_actor), db: Session = Depends(get_db)):
    """Re-run the billing agent: current DB prices, new snapshot, new `bill` message in the chat."""
    order = order_actions.lock_order(db, _customer_only(actor).id)
    if order.status in osm.OPEN_STATES and orders_svc.open_clarifications(db, order.id):
        raise api_error(409, "OPEN_CLARIFICATIONS", "Please answer the open questions before the bill is made.")
    if order.status != "awaiting_confirmation":
        raise osm.invalid_transition(order.status, "awaiting_confirmation")
    shop = db.get(Shop, order.shop_id)
    msg = run_billing(RunCtx(db=db, conversation_id=order.conversation_id, order_id=order.id), order, shop, "manual_quote")
    db.commit()
    return QuoteOut(
        order=orders_svc.serialize_order(db, order), bill=billing_svc.bill_dict(db, order),
        message=MessageOut.model_validate(msg),
    )


@router.post("/{order_id}/confirm", response_model=ConfirmOut)
def confirm(
    order_id: int, body: ConfirmIn, customer: Customer = Depends(get_current_customer), db: Session = Depends(get_db),
):
    order, newly = order_actions.confirm_order(db, order_id, customer, body.address_id, body.payment_method)
    return ConfirmOut(
        order=orders_svc.serialize_order(db, order), message=f"Order #{1000 + order.id} confirmed", newly_confirmed=newly,
    )


@router.post("/{order_id}/cancel", response_model=OrderEnvelope)
def cancel(
    body: CancelIn, actor: tuple[Order, str] = Depends(resolve_actor), db: Session = Depends(get_db),
):
    order, who = actor
    reason = (body.reason or "").strip() or None
    if who == "shopkeeper" and not reason:
        raise api_error(422, "VALIDATION_ERROR", "Please give a reason for cancelling this order.")
    order = order_actions.cancel_order(db, order.id, who, reason)
    return OrderEnvelope(order=orders_svc.serialize_order(db, order))


@router.get("/{order_id}", response_model=CustomerOrderOut)
def read_order(actor: tuple[Order, str] = Depends(resolve_actor), db: Session = Depends(get_db)):
    order = _customer_only(actor)
    return CustomerOrderOut(order=orders_svc.serialize_order(db, order), timeline=timeline_of(db, order.id))

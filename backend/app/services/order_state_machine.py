"""The order state machine (plan 1.2). The ONLY place an order's status is changed.

    draft -> needs_clarification -> awaiting_confirmation -> confirmed -> packing -> out_for_delivery -> delivered
    any pre-delivery state -> cancelled

Who may make which move is part of the rule: the customer confirms or cancels before confirmation, the shopkeeper
moves a confirmed order forward or cancels it, the system moves a draft between its three open states while the
conversation goes on. Every move writes an `order_status_events` row. Moves from `confirmed` onward (and cancel) also
post a system message in the customer's chat; the pre-confirmation moves are already narrated by the bot messages.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.errors import api_error
from app.models import Conversation, Message, Order, OrderStatusEvent
from app.services import language as lang_svc

OPEN_STATES = ("draft", "needs_clarification", "awaiting_confirmation")
STOCK_HELD_STATES = ("confirmed", "packing", "out_for_delivery")  # stock was deducted and not yet given back
TERMINAL_STATES = ("delivered", "cancelled")

# status -> statuses it can move to (any actor)
TRANSITIONS: dict[str, tuple[str, ...]] = {
    "draft": ("needs_clarification", "awaiting_confirmation", "cancelled"),
    "needs_clarification": ("draft", "awaiting_confirmation", "cancelled"),
    "awaiting_confirmation": ("draft", "needs_clarification", "confirmed", "cancelled"),
    "confirmed": ("packing", "cancelled"),
    "packing": ("out_for_delivery", "cancelled"),
    "out_for_delivery": ("delivered", "cancelled"),
    "delivered": (),
    "cancelled": (),
}

_FORWARD = {("confirmed", "packing"), ("packing", "out_for_delivery"), ("out_for_delivery", "delivered")}


def _actor_may(actor: str, frm: str, to: str) -> bool:
    if actor == "system":
        return frm in OPEN_STATES and to in OPEN_STATES
    if actor == "customer":
        return (frm, to) == ("awaiting_confirmation", "confirmed") or (frm in OPEN_STATES and to == "cancelled")
    if actor == "shopkeeper":
        return (frm, to) in _FORWARD or to == "cancelled"
    return False


def can_transition(frm: str, to: str, actor: str = "system") -> bool:
    return to in TRANSITIONS.get(frm, ()) and _actor_may(actor, frm, to)


def allowed_next(status: str, actor: str) -> list[str]:
    return [to for to in TRANSITIONS.get(status, ()) if _actor_may(actor, status, to)]


def invalid_transition(frm: str, to: str):
    return api_error(
        409, "INVALID_TRANSITION",
        f"An order that is {frm.replace('_', ' ')} cannot become {to.replace('_', ' ')}.",
        from_status=frm, to_status=to,
    )


def system_message_text(lang: str, status: str, order_no: int, reason: str | None = None) -> str:
    text = lang_svc.STATUS_MESSAGES[status][lang].format(no=order_no)
    return f"{text} ({reason})" if status == "cancelled" and reason else text


def post_system_message(
    db: Session, order: Order, text: str, kind: str = "order_status", extra: dict | None = None,
) -> Message:
    msg = Message(
        conversation_id=order.conversation_id, sender="system", type="system", content=text,
        meta={"kind": kind, "order_id": order.id, "order_no": 1000 + order.id, "status": order.status, **(extra or {})},
    )
    db.add(msg)
    db.flush()
    return msg


def transition(
    db: Session, order: Order, to: str, actor: str, note: str | None = None, *,
    announce: bool | None = None, text: str | None = None, kind: str = "order_status",
) -> Message | None:
    """Move `order` to `to` or raise 409 INVALID_TRANSITION. Writes the event row and (when announced) the chat
    message; flushes, never commits: the caller owns the transaction.

    `announce` defaults to True from `confirmed` onward and for cancel; `text` overrides the standard message."""
    frm = order.status
    if not can_transition(frm, to, actor):
        raise invalid_transition(frm, to)
    order.status = to
    if to == "confirmed" and order.confirmed_at is None:
        order.confirmed_at = datetime.now(timezone.utc)
    db.add(OrderStatusEvent(order_id=order.id, from_status=frm, to_status=to, actor=actor, note=note))
    db.flush()
    if announce is None:
        announce = to not in OPEN_STATES
    if not announce:
        return None
    conv = db.get(Conversation, order.conversation_id)
    lang = lang_svc.reply_lang(conv.language, conv.script) if conv else "hinglish"
    return post_system_message(db, order, text or system_message_text(lang, to, 1000 + order.id, note), kind)

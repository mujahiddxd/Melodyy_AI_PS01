"""Billing agent: deterministic (no LLM). Quotes the order from current DB prices and posts the bill message."""
from __future__ import annotations

from app.agents.base import RunCtx, agent_step
from app.models import Message, Order, Shop
from app.services import billing as billing_svc


@agent_step("billing")
def run_billing(ctx: RunCtx, order: Order, shop: Shop, reason: str = "awaiting_confirmation") -> Message:
    ctx.record(input={"order_id": order.id, "reason": reason})
    bill = billing_svc.quote_order(ctx.db, order, shop)
    msg = Message(
        conversation_id=ctx.conversation_id, sender="bot", type="bill",
        content=f"Bill for order #{bill['order_no']}: total ₹{bill['total']}",
        meta={"kind": "bill", "order_id": order.id, "bill": bill},
    )
    ctx.db.add(msg)
    ctx.db.flush()
    ctx.record(output={
        "message_id": msg.id, "lines": len(bill["lines"]), "subtotal": bill["subtotal"],
        "delivery_fee": bill["delivery_fee"], "total": bill["total"],
    })
    return msg

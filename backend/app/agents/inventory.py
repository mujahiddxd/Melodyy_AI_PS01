"""Inventory agent (database only). READ ONLY: it converts quantities and checks stock; it never changes stock."""
from __future__ import annotations

from app.agents.base import RunCtx, agent_step
from app.agents.types import ItemPlan, settle
from app.models import Product
from app.services.inventory import evaluate


def evaluate_plan(plan: ItemPlan, catalog: list[Product]) -> ItemPlan:
    m = plan.match
    if m is not None and m.status == "matched" and m.product is not None:
        plan.inv = evaluate(m.product, plan.qty)
    return settle(plan, catalog)


def trace(plan: ItemPlan) -> dict:
    inv = plan.inv
    return {
        "word": plan.word, "status": plan.status, "product_id": plan.product.id if plan.product else None,
        "product_qty": None if plan.product_qty is None else str(plan.product_qty),
        "available_qty": None if plan.available is None else str(plan.available),
        "assumed_qty": plan.assumed_qty, "kind": plan.kind, "confidence": plan.confidence,
        "reason": inv.reason if inv else plan.reason,
        "options": [p.id for p in plan.options],
    }


@agent_step("inventory")
def run_inventory(ctx: RunCtx, plans: list[ItemPlan], catalog: list[Product]) -> list[ItemPlan]:
    ctx.record(input=[{"word": p.word, "match": p.match.status if p.match else None,
                       "product_id": p.match.product.id if p.match and p.match.product else None} for p in plans])
    for p in plans:
        evaluate_plan(p, catalog)
    ctx.record(output=[trace(p) for p in plans])
    return plans

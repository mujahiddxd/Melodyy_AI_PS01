"""Answering a clarification: re-runs Matcher + Inventory for that ONE item (the Clarifier then words what is left).

A chip tap is a deterministic pick (option_product_id is checked against the stored options). Free text goes through
the same fuzzy matcher, restricted to the offered products when there are any; a quantity answer goes through the
unit normalizer. Nothing here trusts LLM text for ids, prices or stock.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.agents.base import RunCtx, agent_step
from app.agents.inventory import evaluate_plan, trace as inventory_trace
from app.agents.matcher import rerank, trace as matcher_trace
from app.agents.parser import quantity_of
from app.agents.types import ItemPlan
from app.models import Clarification, Order, OrderItem, Product
from app.schemas.llm import ParsedItem
from app.services import unit_normalizer as un
from app.services.language import is_skip
from app.services.matcher import CatalogIndex, MatchResult, Candidate, match, norm
from app.services.orders import apply_plan_to_item, open_clarification_for
from app.services.unit_normalizer import NormQty, extract_quantity, normalize


@dataclass
class Decision:
    action: str  # skip | product | qty | narrow | reask
    plan: ItemPlan | None = None
    note: str = ""
    new_clarification: Clarification | None = None
    resolved: list[int] = field(default_factory=list)


def item_qty(item: OrderItem) -> NormQty:
    """The quantity stored on the line, re-reading the customer's words to recover 'vague' (not stored as a column)."""
    if item.quantity_value is not None:
        return NormQty(item.quantity_value, item.unit)
    if normalize(item.raw_text).vague:
        return NormQty(None, item.unit, vague=True)
    return NormQty(None, item.unit, missing=True)


def _plan_for(item: OrderItem) -> ItemPlan:
    parsed = ParsedItem(raw_text=item.raw_text, name_guess=item.name_guess, source_span=item.source_span)
    return ItemPlan(parsed=parsed, qty=item_qty(item))


def _name_tokens(text: str) -> str:
    """The product words of a free-text answer: quantities (digits, number words, fractions) and units removed."""
    drop = (set(un._UNITS) | set(un._FRAC_MULT) | set(un._FRAC_ABS) | set(un._MODIFIERS) | set(un._NUMBER_WORDS)
            | un.VAGUE_WORDS)
    return " ".join(t for t in norm(text).split() if not t.isdigit() and t not in drop)


def _picked(product: Product, why: str) -> MatchResult:
    return MatchResult("matched", product, 1.0, [Candidate(product, 100.0)], reason=why)


def decide(
    clar: Clarification, item: OrderItem, option_product_id: int | None, text: str | None,
    index: CatalogIndex, catalog: list[Product],
) -> Decision:
    by_id = {p.id: p for p in catalog}
    plan = _plan_for(item)
    offered = [o["product_id"] for o in (clar.options or [])]

    if option_product_id is not None:
        product = by_id.get(option_product_id)
        if product is None:
            return Decision("reask", note="option product no longer exists")
        plan.match = _picked(product, "customer tapped this option")
        return Decision("product", plan, "chip")

    text = (text or "").strip()
    if not text:
        return Decision("reask", note="empty answer")
    if is_skip(text):
        return Decision("skip", plan, "customer does not want this item")

    if clar.kind == "vague_qty":
        named = _name_tokens(text)
        if named:  # "1.5 kilo rice" is not the amount of sugar: a reply that clearly names another product is refused
            other = match(named, index)
            theirs = {c.product.id for c in other.candidates}
            if other.status in ("matched", "ambiguous") and item.product_id not in theirs:
                return Decision("reask", note="the reply names a different product")
        q = normalize(text)
        if q.value is None:
            return Decision("reask", note="no quantity found in the answer")
        product = by_id.get(item.product_id) if item.product_id else None
        if product is None:
            return Decision("reask", note="product missing")
        plan.qty = q
        plan.match = _picked(product, "quantity answered")
        plan.match.confidence = float(item.confidence)
        return Decision("qty", plan, "quantity")

    new_qty = extract_quantity(text)
    if new_qty is not None:
        plan.qty = new_qty
    words = _name_tokens(text)
    restricted = clar.kind in ("ambiguous_product", "pack_size") and offered

    if not words:  # only a quantity ("2 kilo", "5 litre")
        if new_qty is None:
            return Decision("reask", note="nothing understood")
        if clar.kind == "out_of_stock" and item.product_id in by_id:
            plan.match = _picked(by_id[item.product_id], "new quantity for the same product")
            plan.match.confidence = float(item.confidence)
            return Decision("qty", plan, "quantity")
        if restricted:
            res = match(item.name_guess, index.restrict(offered), plan.qty)
        else:
            return Decision("reask", note="a quantity alone cannot settle this question")
    else:
        pool = index.restrict(offered) if restricted else index
        res = match(words, pool, plan.qty)
        if res.status == "unmatched" and restricted:
            res = match(words, index, plan.qty)  # maybe they changed their mind to another product
        if res.status == "rerank":
            res = rerank(words, res)

    if res.status == "matched":
        plan.match = res
        return Decision("product", plan, "text")
    if res.status == "ambiguous":
        plan.match = res
        return Decision("narrow", plan, "still ambiguous, narrowed the options")
    return Decision("reask", note="no product found for the answer")


@agent_step("matcher")
def run_answer_matcher(
    ctx: RunCtx, clar: Clarification, item: OrderItem, option_product_id: int | None, text: str | None,
    index: CatalogIndex, catalog: list[Product],
) -> Decision:
    ctx.record(input={"clarification_id": clar.id, "kind": clar.kind, "item": item.name_guess,
                      "option_product_id": option_product_id, "text": text})
    d = decide(clar, item, option_product_id, text, index, catalog)
    out: dict = {"action": d.action, "note": d.note}
    if d.plan is not None and d.plan.match is not None:
        out["match"] = matcher_trace(d.plan)
    ctx.record(output=out)
    return d


@agent_step("inventory")
def run_answer_inventory(ctx: RunCtx, d: Decision, catalog: list[Product]) -> Decision:
    if d.action not in ("product", "qty", "narrow") or d.plan is None:
        ctx.record(input={"action": d.action}, output={"skipped": True})
        return d
    ctx.record(input={"action": d.action, "word": d.plan.word})
    evaluate_plan(d.plan, catalog)
    if d.note == "chip" and d.plan.status == "ambiguous" and d.plan.kind == "pack_size":
        # they tapped a pack that the stated weight does not divide into: take the tap as "1 pack"
        d.plan.qty = NormQty(Decimal(1), "packet")
        d.plan.options, d.plan.kind = [], None
        evaluate_plan(d.plan, catalog)
    ctx.record(output=inventory_trace(d.plan))
    return d


def apply_decision(
    db: Session, order: Order, clar: Clarification, item: OrderItem, d: Decision, lang: str,
    option_product_id: int | None, text: str | None,
) -> None:
    """Write the outcome. The clarification is resolved; a new one opens if the item still needs something."""
    if d.action == "reask" or d.plan is None:
        return
    clar.answer = {"option_product_id": option_product_id} if option_product_id is not None else {"text": text}
    clar.resolved_at = datetime.now(timezone.utc)

    if d.action == "skip":
        item.status, item.product_qty, item.candidates = "removed", None, []
        db.flush()  # autoflush is off: the status refresh must see the resolved clarification
        return

    plan = d.plan
    apply_plan_to_item(item, plan)
    if plan.kind:
        d.new_clarification = open_clarification_for(db, order, item, plan, lang)
    db.flush()

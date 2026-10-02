"""Plain data passed between the agents. No LLM output reaches the database except through these, after validation."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.models import Product
from app.schemas.llm import ParsedItem
from app.services.inventory import InvResult, alternatives, family_key
from app.services.matcher import MatchResult
from app.services.unit_normalizer import NormQty


def pack_label(p: Product) -> str:
    unit = {"l": "L"}.get(p.pack_unit, p.pack_unit)
    size = f"{p.pack_size.normalize():f}"
    return f"per {unit}" if p.sell_mode == "loose" else f"{size} {unit}"


def option_dict(p: Product, score: float | None = None) -> dict:
    """A chip / candidate built from a database row (never from LLM text)."""
    d = {
        "product_id": p.id, "label": p.name, "pack": pack_label(p), "price": f"{p.price:.2f}",
        "stock_status": p.stock_status,
    }
    if score is not None:
        d["score"] = round(score, 1)
    return d


@dataclass
class ItemPlan:
    """One requested item as it moves through matcher -> inventory -> clarifier."""
    parsed: ParsedItem
    qty: NormQty
    match: MatchResult | None = None
    inv: InvResult | None = None
    # resolved state
    status: str = "unmatched"  # matched | ambiguous | out_of_stock | unmatched | vague_qty
    product: Product | None = None
    confidence: float = 0.0
    kind: str | None = None  # clarification kind to open, None when settled
    options: list[Product] = field(default_factory=list)
    candidates: list[dict] = field(default_factory=list)
    available: Decimal | None = None
    product_qty: Decimal | None = None
    normalized_qty: Decimal | None = None
    assumed_qty: bool = False
    reason: str = ""

    @property
    def word(self) -> str:
        return self.parsed.name_guess or self.parsed.raw_text


def settle(plan: ItemPlan, catalog: list[Product]) -> ItemPlan:
    """Combine the matcher result and the inventory result into the item's final status. Deterministic."""
    m, inv = plan.match, plan.inv
    assert m is not None
    plan.reason = m.reason
    if m.status == "unmatched" or m.status == "rerank":  # an unresolved re-rank is treated as unmatched
        plan.status, plan.kind, plan.confidence = "unmatched", "unmatched", round(m.confidence, 2)
        return plan
    if m.status == "ambiguous":
        plan.status, plan.kind, plan.confidence = "ambiguous", m.kind or "ambiguous_product", round(m.confidence, 2)
        plan.options = [c.product for c in m.candidates]
        plan.candidates = [option_dict(c.product, c.score) for c in m.candidates]
        return plan

    # matched: a concrete product, now apply stock
    p = m.product
    assert p is not None and inv is not None
    plan.product, plan.confidence = p, round(m.confidence, 2)
    plan.normalized_qty, plan.assumed_qty = inv.normalized_qty, inv.assumed_qty
    plan.candidates = [option_dict(c.product, c.score) for c in m.candidates]
    if inv.status == "matched":
        plan.status, plan.product_qty = "matched", inv.product_qty
    elif inv.status == "out_of_stock":
        plan.status, plan.kind, plan.available = "out_of_stock", "out_of_stock", inv.available_qty
        plan.product_qty = inv.product_qty
        plan.options = alternatives(p, catalog)
    elif inv.status == "vague_qty":
        plan.status, plan.kind = "vague_qty", "vague_qty"
    else:  # no pack size fits the quantity
        plan.status, plan.kind, plan.product = "ambiguous", "pack_size", None
        fam = family_key(p)
        plan.options = sorted((x for x in catalog if family_key(x) == fam), key=lambda x: x.pack_size)[:6]
        plan.candidates = [option_dict(x) for x in plan.options]
        plan.confidence = round(plan.confidence * 0.7, 2)
    return plan

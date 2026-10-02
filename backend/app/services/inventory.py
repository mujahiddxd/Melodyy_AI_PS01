"""Stock and pack-size arithmetic. READ ONLY in Stage 3: nothing here ever modifies stock.

Inventory is deducted only when the customer confirms the order (Stage 4), inside one transaction.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from app.models import Product
from app.services.unit_normalizer import NormQty, canonical_qty, to_base

D = Decimal
_Q3 = D("0.001")


@dataclass
class InvResult:
    status: str  # matched | out_of_stock | ambiguous | vague_qty
    product_qty: Decimal | None = None  # packs for pack products, base units (kg, l, ...) for loose ones
    normalized_qty: Decimal | None = None  # requested quantity in kg / l / pc / packet
    available_qty: Decimal | None = None  # set when out_of_stock (0 or the partial amount)
    reason: str = ""  # why it is not simply matched
    assumed_qty: bool = False  # the customer gave no quantity: 1 pack was assumed
    kind: str | None = None  # clarification kind the caller should open


def _q3(v: Decimal) -> Decimal:
    return v.quantize(_Q3)


def units_needed(product: Product, qty: NormQty) -> tuple[Decimal | None, str, bool]:
    """(product units, reason, assumed). product units = number of packs for a pack product, base units for a loose
    one. None means the request cannot be converted; `reason` then says why:
    vague | needs_unit | unit_mismatch | no_pack_fits"""
    if qty.vague:
        return None, "vague", False

    value, unit = qty.value, qty.unit
    assumed = False
    if value is None:
        if product.sell_mode == "loose":
            return None, "needs_unit", False  # "onion chahiye": never guess how many kilos
        value, unit, assumed = D(1), None, True

    qdim, qbase = to_base(value, unit)
    pdim, pbase = to_base(product.pack_size, product.pack_unit)

    if product.sell_mode == "loose":
        if qdim == pdim:
            return _q3(qbase / pbase), "", False
        if qdim == "none" and value != value.to_integral():
            return _q3(value * product.pack_size), "", False  # "aadha atta" -> half a unit
        if qdim in ("none", "packet", "count"):
            return None, "needs_unit", False  # "2 onion": kilos? pieces? ask
        return None, "unit_mismatch", False

    # pack products
    if product.pack_unit == "dozen" and qdim == "none":
        qdim = "count"  # "6 anda": six pieces, not six dozen
    if qdim in ("none", "packet"):
        return _q3(value), "", assumed  # a count of packs
    if qdim == pdim:
        packs = qbase / pbase
        if packs >= 1 and packs == packs.to_integral():
            return _q3(packs), "", False
        return None, "no_pack_fits", False
    if qdim == "count":
        return _q3(value), "", False  # "2 piece maggi" -> 2 packs
    return None, "unit_mismatch", False


def pack_fits(product: Product, qty: NormQty) -> bool:
    """True when the requested quantity is a whole number of this pack (e.g. 2 kg with a 1 kg pack)."""
    units, _, _ = units_needed(product, qty)
    return units is not None


def evaluate(product: Product, qty: NormQty) -> InvResult:
    """Convert the request into product units and compare with stock."""
    normalized = canonical_qty(qty)
    units, reason, assumed = units_needed(product, qty)
    if units is None:
        if reason in ("vague", "needs_unit"):
            return InvResult("vague_qty", normalized_qty=normalized, reason=reason, kind="vague_qty")
        return InvResult("ambiguous", normalized_qty=normalized, reason=reason, kind="pack_size")

    stock = product.stock_qty
    if stock <= 0:
        return InvResult("out_of_stock", units, normalized, D(0), "out_of_stock", assumed, "out_of_stock")
    if units > stock:
        return InvResult("out_of_stock", units, normalized, _q3(stock), "short_stock", assumed, "out_of_stock")
    return InvResult("matched", units, normalized, None, "", assumed)


# ---- families and alternatives --------------------------------------------------------------------------
_SIZE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:kg|gm|g|ltr|l|ml|pcs|pc|dozen|packet)\b")


def family_key(product: Product) -> str:
    """Same product sold in several pack sizes shares a key ("Fortune Sunflower Oil 1L" / "... 5L")."""
    s = product.name.lower()
    s = _SIZE.sub(" ", s)
    s = re.sub(r"[^\wऀ-ॿ]+", " ", s)
    s = re.sub(r"\bloose\b", " ", s)
    return " ".join(s.split())


def alternatives(product: Product, catalog: list[Product], limit: int = 5) -> list[Product]:
    """In-stock substitutes for an unavailable product: other pack sizes first, then the same kind of product
    (same category and a shared alias such as "butter"). Database rows only; the LLM never picks these."""
    fam = family_key(product)
    mine = {a.lower() for a in (product.aliases or [])}
    same_pack = [p for p in catalog if p.id != product.id and family_key(p) == fam and p.stock_qty > 0]
    same_kind = [
        p for p in catalog
        if p.id != product.id and p.stock_qty > 0 and family_key(p) != fam and p.category == product.category
        and mine & {a.lower() for a in (p.aliases or [])}
    ]
    same_pack.sort(key=lambda p: abs(p.pack_size - product.pack_size))
    same_kind.sort(key=lambda p: (abs(p.price - product.price), p.id))
    return (same_pack + same_kind)[:limit]


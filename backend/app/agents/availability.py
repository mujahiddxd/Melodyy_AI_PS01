"""Availability questions ("Shakkar hai?"): answered from the shop's catalog and the stock in the database.

READ ONLY and deterministic: nothing is added to the order and no LLM writes the answer, so prices and stock can never
be invented. The parser only supplies the product word; the matcher finds it; stock and price come from `products`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.agents.base import RunCtx, agent_step
from app.agents.matcher import rerank
from app.agents.types import option_dict
from app.models import Product
from app.services.inventory import alternatives, family_key
from app.services.matcher import CatalogIndex, match, norm
from app.services.orders import price_text
from app.services.inventory import evaluate
from app.services import unit_normalizer as un
from app.services.unit_normalizer import NormQty

MAX_LISTED = 6
# question words around the product ("Shakkar hai?", "kya aapke paas atta hai", "Parle-G milega kya")
_QUESTION_WORDS = {
    "hai", "hain", "h", "he", "kya", "aapke", "aap", "apke", "paas", "milega", "milegi", "milta", "milti", "mil",
    "available", "availability", "stock", "me", "mein", "hoga", "hogi", "do", "dena", "is", "there", "any", "have",
    "you", "do", "we", "in", "ka", "ki", "ke", "bhi", "na", "ji", "bhaiya", "bhai", "है", "हैं", "क्या", "आपके", "पास",
    "मिलेगा", "मिलेगी", "मिलता", "में", "आहे", "आहेत", "आहे का", "का", "मिळेल", "मिळेल का", "आहे", "तुमच्याकडे",
    "आपके", "भैया", "भाई", "उपलब्ध",
}


# Is a message a question about stock ("ek kilo biscuit hai", "atta hai kya") or a request ("ek kilo biscuit de do")?
# The LLM's reading of "hai" varies from run to run, so this deterministic check decides when the words are clear.
_QUESTION_MARKERS = {
    "hai", "hain", "milega", "milegi", "milta", "milti", "available", "availability", "stock", "hoga", "hogi", "have",
    "got", "है", "हैं", "मिलेगा", "मिलेगी", "मिलता", "आहे", "आहेत", "मिळेल", "उपलब्ध", "तुमच्याकडे",
}
_ORDER_VERBS = {
    "chahiye", "chahie", "chaiye", "chahiyein", "de", "dena", "dijiye", "dijiyega", "dedo", "bhej", "bhejo", "bhejna",
    "lena", "lunga", "lungi", "add", "order", "want", "need", "send", "give", "bhijwa", "bhijwao", "चाहिए", "दे",
    "देना", "दीजिए", "भेज", "भेजो", "लेना", "पाहिजे", "हवे", "हवा", "हवी", "द्या", "पाठवा", "पाठव",
}


def classify(text: str) -> str | None:
    """"question" | "order" | None (no clear signal). An ordering verb wins over a question word."""
    toks = set(norm(text).split())
    if toks & _ORDER_VERBS:
        return "order"
    if "?" in text or toks & _QUESTION_MARKERS:
        return "question"
    return None


@dataclass
class Fit:
    """"1 kilo biscuit hai?": can that amount be served, and as which pack (e.g. Parle-G 250g x4)."""
    product: Product
    ok: bool
    product_qty: object  # Decimal
    available: object | None  # Decimal when short


@dataclass
class Entry:
    word: str
    products: list[Product] = field(default_factory=list)  # what the shop has under that word (<= 6)
    substitutes: list[Product] = field(default_factory=list)  # in-stock alternatives when everything is out
    fit: Fit | None = None  # only when the customer named a quantity

    @property
    def found(self) -> bool:
        return bool(self.products)


def question_words(text: str) -> str:
    """The product words of a question, used when the parser returned no items."""
    drop = _QUESTION_WORDS | set(un._UNITS) | set(un._NUMBER_WORDS) | set(un._FRAC_MULT) | set(un._FRAC_ABS)
    return " ".join(t for t in norm(text).split() if t not in drop and not t.isdigit())


def _products_of(res, catalog: list[Product]) -> list[Product]:
    """The matched products, each expanded to all its pack sizes (so a 5 kg pack is not hidden behind the 1 kg one)."""
    seeds = [c.product for c in res.candidates] or ([res.product] if res.product else [])
    out: list[Product] = []
    for seed in seeds:
        fam = family_key(seed)
        for p in sorted((x for x in catalog if family_key(x) == fam), key=lambda x: (x.pack_size, x.id)):
            if p not in out:
                out.append(p)
    return out[:MAX_LISTED]


def lookup(
    word: str, brand: str | None, qty: NormQty | None, index: CatalogIndex, catalog: list[Product], budget: list[int],
) -> Entry:
    res = match(word, index, NormQty(None, None, missing=True), brand)
    if res.status == "rerank" and budget[0] > 0:
        budget[0] -= 1
        res = rerank(" ".join(filter(None, [brand, word])), res)  # LLM may only pick among the given candidates
    if res.status == "unmatched":
        return Entry(word)
    products = _products_of(res, catalog)
    entry = Entry(word, products)
    if products and all(p.stock_qty <= 0 for p in products):
        entry.substitutes = alternatives(products[0], catalog, 3)
    if qty is not None and qty.value is not None and not qty.vague:
        fitted = match(word, index, qty, brand)  # which pack serves that quantity
        if fitted.status == "matched" and fitted.product is not None:
            inv = evaluate(fitted.product, qty)
            if inv.status == "matched":
                entry.fit = Fit(fitted.product, True, inv.product_qty, None)
            elif inv.status == "out_of_stock":
                entry.fit = Fit(fitted.product, False, inv.product_qty, inv.available_qty)
    return entry


@agent_step("inventory")
def run_availability(
    ctx: RunCtx, index: CatalogIndex, catalog: list[Product], asks: list[tuple[str, str | None, NormQty | None]],
) -> list[Entry]:
    ctx.record(input={"purpose": "availability question (read only, nothing is added to the order)",
                      "asks": [{"word": w, "brand": b, "qty": None if q is None or q.value is None else f"{q.value} {q.unit or ''}".strip()}
                               for w, b, q in asks]})
    budget = [2]
    entries = [lookup(w, b, q, index, catalog, budget) for w, b, q in asks[:5]]
    ctx.record(output=[
        {"word": e.word, "found": e.found,
         "products": [{"product_id": p.id, "name": p.name, "stock_qty": str(p.stock_qty), "price": f"{p.price:.2f}"}
                      for p in e.products],
         "substitutes": [p.id for p in e.substitutes],
         "fit": None if e.fit is None else {"product_id": e.fit.product.id, "ok": e.fit.ok,
                                            "product_qty": str(e.fit.product_qty)}}
        for e in entries
    ])
    return entries


def label(p: Product) -> str:
    return f"{p.name} ({price_text(option_dict(p))})"


def qty_label(q: NormQty) -> str:
    return f"{q.value:g} {UNIT_SHOWN.get(q.unit or '', q.unit or '')}".strip()


UNIT_SHOWN = {"l": "L"}


def left_text(p: Product) -> str:
    q = f"{p.stock_qty.normalize():f}"
    return f"{q} {({'l': 'L'}.get(p.pack_unit, p.pack_unit))}" if p.sell_mode == "loose" else q

"""Catalog matcher: rapidfuzz over name + brand + aliases of the shop's active products.

Rules (plan Stage 3):
  top >= 85 and runner-up >= 10 lower      -> matched
  several products of one generic type     -> ambiguous (one candidate per product family, max 6)
  several pack sizes of one product        -> pick the pack that fits the quantity, else ambiguous
  60 <= top < 85                           -> "rerank": the caller asks the LLM to choose among these candidate ids
  top < 60                                 -> unmatched
Confidence = score / 100, penalised for pack-size guesses and ambiguity.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from app.models import Product
from app.services.inventory import family_key, pack_fits
from app.services.unit_normalizer import NormQty, to_base

MATCH_MIN = 85
RERANK_MIN = 60
RUNNER_UP_GAP = 10
TYPO_MIN = 70  # a per-field character similarity below this is noise ("oats" ~ "potato" = 60)
MAX_CANDIDATES = 6
PACK_DEFAULT_PENALTY = 0.8  # a pack size was chosen by default (no size said)
AMBIGUOUS_PENALTY = 0.7

_STOPWORDS = {
    "bhaiya", "bhaiyya", "bhai", "dada", "kaka", "please", "pls", "plz", "chahiye", "chahie", "chaiye", "hai", "ka",
    "ki", "ke", "wala", "wali", "wale", "vala", "bhi", "aur", "de", "dena", "dijiye", "भैया", "भाई", "चाहिए", "का",
    "की", "के", "वाला", "वाली", "भी", "और", "आणि", "पाहिजे", "हवे", "द्या", "ला",
}
_CLEAN = re.compile(r"[^\wऀ-ॿ]+")


def norm(s: str) -> str:
    return " ".join(_CLEAN.sub(" ", s.lower()).split())


def query_tokens(s: str) -> str:
    return " ".join(t for t in norm(s).split() if t not in _STOPWORDS)


@dataclass
class Candidate:
    product: Product
    score: float


@dataclass
class MatchResult:
    status: str  # matched | ambiguous | rerank | unmatched
    product: Product | None = None
    confidence: float = 0.0
    candidates: list[Candidate] = field(default_factory=list)
    kind: str | None = None  # for ambiguous: ambiguous_product | pack_size
    reason: str = ""
    pack_defaulted: bool = False


class _Entry:
    __slots__ = ("product", "text", "fields", "family", "brand")

    def __init__(self, p: Product):
        self.product = p
        self.text = norm(" ".join([p.name, p.brand or "", *(p.aliases or [])]))
        self.fields = [norm(p.name), *(norm(a) for a in (p.aliases or []))]
        self.family = family_key(p)
        self.brand = norm(p.brand or "")


class CatalogIndex:
    def __init__(self, products: list[Product]):
        self.entries = [_Entry(p) for p in products if p.is_active is not False]
        self.by_id = {e.product.id: e for e in self.entries}

    def restrict(self, product_ids: list[int]) -> "CatalogIndex":
        sub = CatalogIndex([])
        sub.entries = [e for e in self.entries if e.product.id in set(product_ids)]
        sub.by_id = {e.product.id: e for e in sub.entries}
        return sub

    def vocabulary(self) -> set[str]:
        return {t for e in self.entries for t in e.text.split()}

    def scores(self, query: str) -> list[tuple[_Entry, float]]:
        q = query_tokens(query)
        if not q:
            return []
        out = []
        for e in self.entries:
            # token_set_ratio over the whole text (specific queries), fuzz.ratio per field (typos: "shakar")
            typo = max(fuzz.ratio(q, f) for f in e.fields)
            s = max(fuzz.token_set_ratio(q, e.text), typo if typo >= TYPO_MIN else 0)
            out.append((e, float(s)))
        out.sort(key=lambda x: (-x[1], x[0].product.pack_size, x[0].product.id))
        return out


def _representative(group: list[_Entry]) -> _Entry:
    """Smallest pack of a family, preferring one that is in stock."""
    in_stock = [e for e in group if e.product.stock_qty > 0]
    return min(in_stock or group, key=lambda e: (e.product.pack_size, e.product.id))


def _brand_filter(families: dict[str, list[_Entry]], query: str, brand_guess: str | None) -> dict[str, list[_Entry]]:
    words = set(query_tokens(" ".join(filter(None, [brand_guess, query]))).split())
    keep = {}
    for fam, group in families.items():
        brand = group[0].brand
        if brand and any(fuzz.ratio(brand, w) >= 80 or w in brand.split() for w in words if len(w) >= 3):
            keep[fam] = group
    return keep or families


def _weighable(qty: NormQty) -> bool:
    return qty.value is not None and to_base(qty.value, qty.unit)[0] in ("mass", "volume")


def _choose_pack(packs: list[_Entry], qty: NormQty) -> tuple[_Entry | None, bool]:
    """Pick one pack size of a product. (entry, defaulted). None when no size fits the requested weight/volume."""
    if _weighable(qty):
        fitting = [e for e in packs if pack_fits(e.product, qty)]
        if fitting:
            return max(fitting, key=lambda e: e.product.pack_size), False  # 2 kg + 1 kg and 5 kg packs -> 2 x 1 kg
        return None, False
    return min(packs, key=lambda e: (e.product.pack_size, e.product.id)), True  # "ek butter": smallest pack


def match(
    query: str,
    index: CatalogIndex,
    qty: NormQty | None = None,
    brand_guess: str | None = None,
) -> MatchResult:
    qty = qty or NormQty(None, None, missing=True)
    scored = index.scores(" ".join(filter(None, [brand_guess, query])))
    if not scored or scored[0][1] < RERANK_MIN:
        return MatchResult("unmatched", confidence=(scored[0][1] / 100 if scored else 0.0), reason="no product close enough")

    top = scored[0][1]
    if top < MATCH_MIN:
        cands = [Candidate(e.product, s) for e, s in scored if s >= RERANK_MIN][:MAX_CANDIDATES]
        return MatchResult("rerank", confidence=top / 100, candidates=cands, reason="score between 60 and 85")

    cluster = [(e, s) for e, s in scored if s >= top - RUNNER_UP_GAP]
    if len(cluster) == 1:
        e, s = cluster[0]
        return MatchResult("matched", e.product, s / 100, [Candidate(e.product, s)], reason="single clear match")

    score_of = {e.product.id: s for e, s in cluster}
    families: dict[str, list[_Entry]] = {}
    for e, _ in cluster:
        families.setdefault(e.family, []).append(e)

    if len(families) > 1:
        families = _brand_filter(families, query, brand_guess)
    if len(families) > 1 and _weighable(qty):
        loose = {f: g for f, g in families.items() if all(e.product.sell_mode == "loose" for e in g)}
        if len(loose) == 1:  # "2 kilo atta": the loose atta answers it, no brand was named
            families = loose

    if len(families) > 1:
        reps = [_representative(g) for g in families.values()][:MAX_CANDIDATES]
        cands = [Candidate(e.product, score_of[e.product.id]) for e in reps]
        return MatchResult(
            "ambiguous", confidence=round(top / 100 * AMBIGUOUS_PENALTY, 2), candidates=cands,
            kind="ambiguous_product", reason=f"{len(families)} products fit",
        )

    packs = next(iter(families.values()))
    if len(packs) == 1:
        e = packs[0]
        return MatchResult("matched", e.product, score_of[e.product.id] / 100, [Candidate(e.product, score_of[e.product.id])])

    chosen, defaulted = _choose_pack(packs, qty)
    cands = [Candidate(e.product, score_of[e.product.id]) for e in sorted(packs, key=lambda e: e.product.pack_size)][:MAX_CANDIDATES]
    if chosen is None:
        return MatchResult(
            "ambiguous", confidence=round(top / 100 * AMBIGUOUS_PENALTY, 2), candidates=cands,
            kind="pack_size", reason="no pack size fits the quantity",
        )
    conf = score_of[chosen.product.id] / 100 * (PACK_DEFAULT_PENALTY if defaulted else 1.0)
    return MatchResult(
        "matched", chosen.product, round(conf, 2), cands,
        reason="smallest pack chosen, no size said" if defaulted else "pack size fits the quantity",
        pack_defaulted=defaulted,
    )

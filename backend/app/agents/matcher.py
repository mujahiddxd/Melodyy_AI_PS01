"""Matcher agent: deterministic fuzzy match (services/matcher.py). Only the 60-85 band asks the LLM, and only to choose
among the candidate ids it is given; any other id is rejected."""
from __future__ import annotations

import json
import logging

from app.agents.base import RunCtx, agent_step
from app.agents.types import ItemPlan, pack_label
from app.llm.client import LLMError, complete_json
from app.llm.prompts import load_prompt
from app.schemas.llm import RerankOut
from app.services.matcher import AMBIGUOUS_PENALTY, Candidate, CatalogIndex, MatchResult, match

log = logging.getLogger("hod.agents.matcher")
RERANK_BUDGET = 3  # LLM re-rank calls per message; beyond that the customer is asked to choose
MIN_RERANK_CONFIDENCE = 0.6


def rerank(query: str, res: MatchResult) -> MatchResult:
    """Ask the LLM to pick among res.candidates. Never raises: failure -> the customer chooses (ambiguous)."""
    ids = {c.product.id: c for c in res.candidates}
    payload = {
        "customer_words": query,
        "candidates": [
            {"id": c.product.id, "name": c.product.name, "brand": c.product.brand, "pack": pack_label(c.product)}
            for c in res.candidates
        ],
    }
    try:
        out = complete_json(load_prompt("rerank"), json.dumps(payload, ensure_ascii=False), RerankOut,
                            temperature=0.0, mock=("rerank", query))
    except LLMError as e:
        log.warning("re-rank failed, asking the customer: %s", e)
        return _ask_customer(res, "re-rank unavailable")

    choice = out.choice_product_id
    if choice is None:
        return MatchResult("unmatched", confidence=res.confidence, reason=f"re-rank: none ({out.reason[:80]})")
    if choice not in ids:  # an id we never offered: reject it, never trust it
        log.warning("re-rank returned an id outside the candidate list: rejected")
        return _ask_customer(res, "re-rank returned an unknown id (rejected)")
    if out.confidence < MIN_RERANK_CONFIDENCE:
        return _ask_customer(res, "re-rank not confident")
    cand = ids[choice]
    conf = round(0.5 * cand.score / 100 + 0.5 * out.confidence, 2)
    return MatchResult("matched", cand.product, conf, [Candidate(cand.product, cand.score)],
                       reason=f"LLM re-rank: {out.reason[:80]}")


def _ask_customer(res: MatchResult, why: str) -> MatchResult:
    return MatchResult(
        "ambiguous", confidence=round(res.confidence * AMBIGUOUS_PENALTY, 2), candidates=res.candidates[:6],
        kind="ambiguous_product", reason=why,
    )


def trace(plan: ItemPlan) -> dict:
    m = plan.match
    assert m is not None
    return {
        "word": plan.word, "status": m.status, "product_id": m.product.id if m.product else None,
        "confidence": round(m.confidence, 2), "reason": m.reason,
        "candidates": [{"product_id": c.product.id, "name": c.product.name, "score": round(c.score, 1)}
                       for c in m.candidates],
    }


@agent_step("matcher")
def run_matcher(ctx: RunCtx, index: CatalogIndex, plans: list[ItemPlan]) -> list[ItemPlan]:
    ctx.record(input=[{"word": p.word, "brand": p.parsed.brand_guess,
                       "qty": {"value": None if p.qty.value is None else str(p.qty.value), "unit": p.qty.unit,
                               "vague": p.qty.vague}} for p in plans])
    budget = RERANK_BUDGET
    for p in plans:
        res = match(p.word, index, p.qty, p.parsed.brand_guess)
        if res.status == "rerank":
            if budget > 0:
                budget -= 1
                res = rerank(" ".join(filter(None, [p.parsed.brand_guess, p.word])), res)
            else:
                res = _ask_customer(res, "re-rank budget used up")
        p.match = res
    ctx.record(output=[trace(p) for p in plans])
    return plans

"""Parser agent: one LLM call (temperature 0) -> intent + items. Then the deterministic unit normalizer turns the
quantity words into numbers. The LLM never sees prices and never returns product ids."""
from __future__ import annotations

import json
from dataclasses import dataclass

from app.agents.base import RunCtx, agent_step
from app.agents.intake import IntakeResult
from app.llm.client import complete_json
from app.llm.prompts import load_prompt
from app.schemas.llm import ParsedItem, ParserOut
from app.services.unit_normalizer import NormQty, extract_quantity, normalize

MAX_ITEMS = 30


class TooManyItems(Exception):
    """The message lists more than MAX_ITEMS items."""


@dataclass
class ParseResult:
    language: str
    script: str
    intent: str
    items: list[tuple[ParsedItem, NormQty]]
    delivery_time_text: str | None
    notes: str | None


def _clean_span(text: str, item: ParsedItem) -> list[int] | None:
    """source_span are offsets into the original text; dropped when out of bounds (try to locate raw_text instead)."""
    sp = item.source_span
    if sp and len(sp) == 2 and 0 <= sp[0] < sp[1] <= len(text):
        return [int(sp[0]), int(sp[1])]
    if item.raw_text:
        i = text.lower().find(item.raw_text.lower())
        if i >= 0:
            return [i, i + len(item.raw_text)]
    return None


def quantity_of(item: ParsedItem) -> NormQty:
    """Quantity words -> numbers (Appendix C). Falls back to the raw text when the LLM left the fields empty."""
    q = normalize(item.quantity_text, item.quantity_value, item.unit_text, item.raw_text)
    if item.is_vague and q.value is None:
        return NormQty(None, q.unit, vague=True)
    if q.missing and item.raw_text:
        if normalize(item.raw_text).vague:
            return NormQty(None, None, vague=True)
        found = extract_quantity(item.raw_text)
        if found is not None:
            return found
    return q


@agent_step("parser")
def run_parser(
    ctx: RunCtx,
    text: str,
    intake: IntakeResult,
    categories: list[str],
    order_summary: str,
    open_questions: list[str],
) -> ParseResult:
    payload = {"message": text, "catalog_categories": categories, "current_order": order_summary}
    if open_questions:
        payload["open_questions"] = open_questions
    ctx.record(input=payload)

    out = complete_json(load_prompt("parser"), json.dumps(payload, ensure_ascii=False), ParserOut,
                        temperature=0.0, mock=("parser", text))

    raw_items = [i for i in out.items if (i.name_guess or i.raw_text)]
    if len(raw_items) > MAX_ITEMS:
        raise TooManyItems(f"{len(raw_items)} items")

    items: list[tuple[ParsedItem, NormQty]] = []
    for it in raw_items:
        if not it.name_guess:
            it.name_guess = it.raw_text
        if not it.raw_text:
            it.raw_text = it.name_guess
        it.source_span = _clean_span(text, it)
        items.append((it, quantity_of(it)))

    res = ParseResult(out.language, out.script, out.intent, items, out.delivery_time_text, out.notes)
    ctx.record(output={
        "language": out.language, "script": out.script, "intent": out.intent,
        "delivery_time_text": out.delivery_time_text, "notes": out.notes,
        "items": [
            {"raw_text": i.raw_text, "name_guess": i.name_guess, "brand_guess": i.brand_guess,
             "quantity": {"value": None if q.value is None else str(q.value), "unit": q.unit, "vague": q.vague,
                          "missing": q.missing},
             "source_span": i.source_span}
            for i, q in items
        ],
    })
    return res

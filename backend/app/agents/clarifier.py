"""Clarifier agent: ONE combined message for everything still open, in the customer's language and script.

The LLM only words the question. It is given the exact options (read from the database) and its output is checked:
right script, no rupee amount that is not in the options. On any failure the deterministic template is used.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from app.agents.base import RunCtx, agent_step
from app.llm.client import LLMError, complete_json
from app.llm.prompts import load_prompt
from app.schemas.llm import ClarifierOut
from app.services.language import combined_message, reply_lang

log = logging.getLogger("hod.agents.clarifier")
_RUPEE = re.compile(r"₹\s*(\d+(?:\.\d+)?)")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_DEVA = re.compile(r"[ऀ-ॿ]")
_LATIN = re.compile(r"[A-Za-z]")


@dataclass
class ClarifyResult:
    message: str
    source: str  # llm | template


def _num(s: str) -> str:
    return f"{float(s):g}"


def _valid(message: str, script: str, facts: list[dict]) -> str | None:
    """None when the message is acceptable, else the reason it is rejected."""
    deva, latin = len(_DEVA.findall(message)), len(_LATIN.findall(message))
    if script == "devanagari" and deva == 0:
        return "wrong script (expected Devanagari)"
    if script == "latin" and deva > latin:
        return "wrong script (expected Roman letters)"
    allowed = {_num(n) for f in facts for o in f.get("options", []) for n in _NUMBER.findall(o["price"])}
    for amount in _RUPEE.findall(message):
        if _num(amount) not in allowed:
            return f"amount ₹{amount} is not in the options"
    return None


@agent_step("clarifier")
def run_clarifier(
    ctx: RunCtx, language: str, script: str, shop_name: str, facts: list[dict], customer_text: str,
) -> ClarifyResult:
    lang = reply_lang(language, script)
    payload = {"language": language, "script": script, "shop": shop_name, "items": facts}
    ctx.record(input=payload)

    source, reason = "llm", None
    try:
        out = complete_json(load_prompt("clarifier"), json.dumps(payload, ensure_ascii=False), ClarifierOut,
                            temperature=0.3, mock=("clarifier", customer_text))
        reason = _valid(out.message, script, facts)
        message = out.message.strip()
    except LLMError as e:
        message, reason = "", f"LLM unavailable: {e}"
    if reason:
        log.info("clarifier using the template (%s)", reason)
        message, source = combined_message(lang, facts), "template"

    ctx.record(output={"message": message, "source": source, "fallback_reason": reason})
    return ClarifyResult(message, source)

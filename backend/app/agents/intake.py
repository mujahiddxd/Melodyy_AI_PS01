"""Intake agent: language + script + gibberish / irrelevant check. A cheap heuristic decides the clear cases; the LLM is
only asked when the text has no recognisable word, so most messages cost no extra call."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from app.agents.base import RunCtx, agent_step
from app.llm.client import LLMError, complete_json
from app.llm.prompts import load_prompt
from app.schemas.llm import IntakeOut
from app.services.language import assess

log = logging.getLogger("hod.agents.intake")


@dataclass
class IntakeResult:
    language: str
    script: str
    category: str  # order | gibberish | other | wait | confirm | decline
    source: str  # heuristic | llm | heuristic_fallback
    confident: bool = False  # language decided from marker words (or by the LLM), not by default


@agent_step("intake")
def run_intake(ctx: RunCtx, text: str, catalog_vocab: set[str]) -> IntakeResult:
    a = assess(text, catalog_vocab)
    ctx.record(input={"text": text})

    if a.verdict == "gibberish":
        res = IntakeResult(a.language, a.script, "gibberish", "heuristic", a.confident)
    elif a.verdict in ("wait", "confirm", "decline"):
        res = IntakeResult(a.language, a.script, a.verdict, "heuristic", a.confident)
    elif a.verdict == "ok":
        res = IntakeResult(a.language, a.script, "order", "heuristic", a.confident)
    else:  # uncertain: ask the LLM (temperature 0)
        try:
            out = complete_json(load_prompt("intake"), f"Message: {text}", IntakeOut, mock=("intake", text))
            # the script is decided by the letters, not by the model
            res = IntakeResult(out.language, a.script, out.category, "llm", True)
        except LLMError as e:
            log.warning("intake LLM failed, letting the parser decide: %s", e)
            res = IntakeResult(a.language, a.script, "order", "heuristic_fallback", a.confident)

    ctx.record(output={"language": res.language, "script": res.script, "category": res.category,
                       "source": res.source, "confident": res.confident, "heuristic": a.reason})
    return res

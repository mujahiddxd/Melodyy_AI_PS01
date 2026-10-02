"""OCR agent: Vision LLM call -> legible boolean + transcribed lines.
Input is untrusted: validated by OcrOut schema.
"""
from __future__ import annotations

import logging

from app.agents.base import RunCtx, agent_step
from app.llm.client import complete_vision_json
from app.llm.prompts import load_prompt
from app.schemas.llm import OcrOut

log = logging.getLogger("hod.agents.ocr")


@agent_step("ocr")
def run_ocr(ctx: RunCtx, image_bytes: bytes, mime_type: str = "image/jpeg") -> OcrOut:
    ctx.record(input={"image_size_bytes": len(image_bytes), "mime_type": mime_type})
    system_prompt = load_prompt("ocr")
    user_prompt = "Transcribe this handwritten Indian grocery shopping list line by line. Return JSON with legible (boolean) and lines (list of strings)."
    out = complete_vision_json(system_prompt, user_prompt, image_bytes, mime_type, OcrOut, temperature=0.0)
    # clean empty lines
    out.lines = [line.strip() for line in out.lines if line and line.strip()]
    if not out.lines:
        out.legible = False
    ctx.record(output={"legible": out.legible, "line_count": len(out.lines), "lines": out.lines})
    return out

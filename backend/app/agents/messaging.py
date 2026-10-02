"""Messaging agent: stores the bot's reply in the conversation (the request transaction commits it)."""
from __future__ import annotations

from app.agents.base import RunCtx, agent_step
from app.models import Message


@agent_step("messaging")
def run_messaging(ctx: RunCtx, text: str, meta: dict | None = None, sender: str = "bot") -> Message:
    ctx.record(input={"text": text, "meta": meta})
    msg = Message(conversation_id=ctx.conversation_id, sender=sender, type="text", content=text, meta=meta or None)
    ctx.db.add(msg)
    ctx.db.flush()
    ctx.record(output={"message_id": msg.id, "sender": sender})
    return msg

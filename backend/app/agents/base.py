"""Agent plumbing: the @agent_step decorator writes one agent_runs row per step (running -> success / error).

Rows are written with their own short database session and committed immediately, so a failed step keeps its error
row even when the request's order transaction is rolled back, and "running" is visible while the step works.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Callable

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import AgentRun

log = logging.getLogger("hod.agents")
_MAX_JSON_CHARS = 20000


def jsonable(obj: Any) -> Any:
    """Round-trip through JSON so the value is safe for a JSONB column (Decimals, dataclasses, ... become text)."""
    try:
        text = json.dumps(obj, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        text = json.dumps(str(obj))
    if len(text) > _MAX_JSON_CHARS:
        return {"truncated": True, "preview": text[:2000]}
    return json.loads(text)


@dataclass
class RunCtx:
    """Per-request context handed to every agent."""
    db: Session
    conversation_id: int
    message_id: int | None = None
    order_id: int | None = None  # only a COMMITTED order; runs are linked to a new order after the commit
    run_ids: list[int] = field(default_factory=list)
    _rec: dict = field(default_factory=dict)

    def record(self, *, input: Any = None, output: Any = None) -> None:
        """Called by an agent to say what it saw and produced (stored in agent_runs.input / output)."""
        if input is not None:
            self._rec["input"] = input
        if output is not None:
            self._rec["output"] = output

    def skipped(self, agent: str, reason: str) -> None:
        """Write a 'skipped' row for a step that had nothing to do."""
        with SessionLocal() as s:
            row = AgentRun(
                conversation_id=self.conversation_id, order_id=self.order_id, message_id=self.message_id,
                agent=agent, status="skipped", input=None, output=jsonable({"reason": reason}), duration_ms=0,
            )
            s.add(row)
            s.commit()
            self.run_ids.append(row.id)


def _safe_error(exc: Exception) -> str:
    return f"{type(exc).__name__}: {str(exc)[:300]}"


def agent_step(name: str) -> Callable:
    """@agent_step("parser"): wraps `fn(ctx, ...)` so its run is logged in agent_runs."""

    def deco(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(ctx: RunCtx, *args, **kwargs):
            with SessionLocal() as s:
                row = AgentRun(
                    conversation_id=ctx.conversation_id, order_id=ctx.order_id, message_id=ctx.message_id,
                    agent=name, status="running",
                )
                s.add(row)
                s.commit()
                run_id = row.id
            ctx.run_ids.append(run_id)
            ctx._rec = {}
            t0 = time.perf_counter()

            def finish(status: str, error: str | None = None) -> None:
                ms = int((time.perf_counter() - t0) * 1000)
                try:
                    with SessionLocal() as s2:
                        s2.execute(
                            update(AgentRun).where(AgentRun.id == run_id).values(
                                status=status, error=error, duration_ms=ms,
                                input=jsonable(ctx._rec.get("input")), output=jsonable(ctx._rec.get("output")),
                            )
                        )
                        s2.commit()
                except Exception:  # never let logging break the order flow
                    log.exception("could not finish agent_run %s", run_id)

            try:
                result = fn(ctx, *args, **kwargs)
            except Exception as exc:
                finish("error", _safe_error(exc))
                raise
            finish("success")
            return result

        return wrapper

    return deco

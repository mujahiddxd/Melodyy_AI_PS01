"""Single entry point for LLM calls. Output is untrusted: always validated by a Pydantic schema."""
import json
import logging
from typing import Type, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.config import get_settings

log = logging.getLogger("hod.llm")
T = TypeVar("T", bound=BaseModel)

TIMEOUT_S = 20
# Canned outputs for the demo messages (filled in from Stage 3). Keyed by lowercased user text.
MOCK_FIXTURES: dict[str, dict] = {}


class LLMError(Exception):
    """Raised when the LLM call fails or its output does not validate."""


def _call_provider(system: str, user: str) -> str:
    s = get_settings()
    if not s.llm_api_key:
        raise LLMError("LLM_API_KEY is not set")
    if s.llm_provider == "openai":
        r = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {s.llm_api_key}"},
            json={
                "model": s.llm_model_text,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=TIMEOUT_S,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    raise LLMError(f"LLM_PROVIDER '{s.llm_provider}' is not implemented yet")


def complete_json(system: str, user: str, schema: Type[T]) -> T:
    """Call the LLM, parse JSON, validate with `schema`. One retry. Raises LLMError on failure."""
    if get_settings().llm_mock:
        fixture = MOCK_FIXTURES.get(user.strip().lower())
        if fixture is None:
            raise LLMError("LLM_MOCK=true and no fixture for this input")
        return schema.model_validate(fixture)

    last: Exception | None = None
    for attempt in range(2):
        try:
            return schema.model_validate(json.loads(_call_provider(system, user)))
        except (httpx.HTTPError, json.JSONDecodeError, ValidationError, KeyError, LLMError) as e:
            last = e
            log.warning("LLM attempt %d failed: %s", attempt + 1, type(e).__name__)
    raise LLMError(f"LLM call failed: {type(last).__name__}")

"""Single entry point for LLM calls. Output is untrusted: always validated by a Pydantic schema.

complete_json(system, user, Schema, temperature=0, mock=("parser", text))
  - JSON mode, 20 s timeout per HTTP call, Pydantic validation.
  - Fallbacks: every API key in LLM_API_KEY / LLM_API_KEYS is tried in order; a key that is rejected (401/403/400
    invalid) or rate limited (429) is put on cooldown so later calls skip it. If a model is overloaded (503) the next
    model in LLM_MODEL_FALLBACKS is tried. Keys are never logged.
  - LLM_MOCK=true returns canned fixtures (app/llm/fixtures.py) for the 6 demo messages and never touches the network.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Type, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.config import get_settings

log = logging.getLogger("hod.llm")
T = TypeVar("T", bound=BaseModel)

TIMEOUT_S = 20
MAX_ATTEMPTS = 6  # (key, model) pairs tried per call, including the one retry
CALL_BUDGET_S = 45  # stop starting new attempts after this long
COOLDOWN_AUTH_S = 3600
COOLDOWN_RATE_S = 60

# monotonic time until which something is skipped. Keyed by `key` (rejected key: skipped for every model) or by
# `(key, model)` (rate limit / overloaded model: only that pair is skipped, so a throttled model is not retried first).
_cooldown: dict = {}
COOLDOWN_MODEL_S = 20


class LLMError(Exception):
    """Raised when every attempt failed or the output does not validate. The message is safe to show in logs."""


class _Retryable(Exception):
    """A failed attempt. cooldown: seconds to skip it afterwards. scope: "key" (whole key) or "pair" (this key + model).
    model_level: the model itself is failing, so other keys on it are not tried in this call."""

    def __init__(self, reason: str, cooldown: float = 0, model_level: bool = False, scope: str = "key"):
        super().__init__(reason)
        self.reason, self.cooldown, self.model_level, self.scope = reason, cooldown, model_level, scope


def _fence_stripped(text: str) -> str:
    t = text.strip()
    m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", t, re.S)
    return m.group(1) if m else t


def _classify(status: int) -> _Retryable:
    if status in (401, 403):
        return _Retryable(f"http {status}", COOLDOWN_AUTH_S)
    if status == 400:
        return _Retryable("http 400", COOLDOWN_AUTH_S)  # bad key or bad request: do not hammer it
    if status == 404:
        return _Retryable("http 404 (model unavailable)", COOLDOWN_AUTH_S, model_level=True, scope="pair")
    if status == 429:
        return _Retryable("http 429", COOLDOWN_RATE_S, scope="pair")
    return _Retryable(f"http {status}", COOLDOWN_MODEL_S if status >= 500 else 0, model_level=status >= 500, scope="pair")


def _post(url: str, headers: dict, body: dict) -> dict:
    try:
        r = httpx.post(url, headers=headers, json=body, timeout=TIMEOUT_S)
    except httpx.TimeoutException:
        raise _Retryable("timeout", COOLDOWN_MODEL_S, model_level=True, scope="pair")
    except httpx.HTTPError as e:
        raise _Retryable(type(e).__name__)
    if r.status_code != 200:
        raise _classify(r.status_code)
    try:
        return r.json()
    except ValueError:
        raise _Retryable("non-json response")


def _call_gemini(key: str, model: str, system: str, user: str, temperature: float) -> str:
    data = _post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        {"x-goog-api-key": key},
        {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": temperature, "responseMimeType": "application/json"},
        },
    )
    cands = data.get("candidates") or []
    if not cands:
        raise _Retryable("no candidates (blocked or empty)")
    parts = (cands[0].get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    if not text.strip():
        raise _Retryable("empty output")
    return text


def _call_openai(key: str, model: str, system: str, user: str, temperature: float) -> str:
    data = _post(
        "https://api.openai.com/v1/chat/completions",
        {"Authorization": f"Bearer {key}"},
        {
            "model": model,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        },
    )
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise _Retryable("unexpected response shape")


_PROVIDERS = {"gemini": _call_gemini, "openai": _call_openai}


def _mock(schema: Type[T], mock: tuple[str, str] | None) -> T:
    from app.llm.fixtures import FIXTURES  # imported lazily: only mock mode needs it

    if mock is None:
        raise LLMError("LLM_MOCK=true and this call has no fixture key")
    task, key = mock
    fixture = FIXTURES.get(task, {}).get(key.strip().lower())
    if fixture is None:
        raise LLMError(f"LLM_MOCK=true and no {task} fixture for this input")
    try:
        return schema.model_validate(fixture)
    except ValidationError as e:
        raise LLMError(f"mock fixture for {task} does not match the schema: {e.error_count()} errors")


def complete_json(
    system: str,
    user: str,
    schema: Type[T],
    *,
    temperature: float = 0.0,
    mock: tuple[str, str] | None = None,
) -> T:
    """Call the LLM, parse JSON, validate with `schema`. Raises LLMError when nothing usable came back."""
    s = get_settings()
    if s.llm_mock:
        return _mock(schema, mock)

    call = _PROVIDERS.get(s.llm_provider)
    if call is None:
        raise LLMError(f"LLM_PROVIDER '{s.llm_provider}' is not supported (use gemini or openai)")
    keys, models = s.llm_keys, s.llm_models
    if not keys:
        raise LLMError("LLM_API_KEY is not set")
    if not models:
        raise LLMError("LLM_MODEL_TEXT is not set")

    started = time.monotonic()
    attempts = 0
    last = "no attempt made"
    plan = models if len(models) > 1 else models * 2  # one model only: the second pass is the one retry
    pairs = [(i, m, k) for i, m in enumerate(plan) for k in keys]

    def cooling(m: str, k: str) -> bool:
        return started < _cooldown.get(k, 0) or started < _cooldown.get((k, m), 0)

    # pairs that are not cooling down first (so a throttled model is skipped), the cooling ones only as a last resort
    ordered = [p for p in pairs if not cooling(p[1], p[2])] + [p for p in pairs if cooling(p[1], p[2])]
    failed_models: set[int] = set()  # plan positions whose model failed in this call
    for pos, model, key in ordered:
        if pos in failed_models:
            continue
        if attempts >= MAX_ATTEMPTS or time.monotonic() - started > CALL_BUDGET_S:
            break
        attempts += 1
        label = f"key#{keys.index(key) + 1}/{model}"
        try:
            raw = call(key, model, system, user, temperature)
            return schema.model_validate(json.loads(_fence_stripped(raw)))
        except _Retryable as e:
            last = f"{label}: {e.reason}"
            if e.cooldown:
                _cooldown[key if e.scope == "key" else (key, model)] = time.monotonic() + e.cooldown
            log.warning("LLM attempt %d failed (%s)", attempts, last)
            if e.model_level:
                failed_models.add(pos)
                time.sleep(0.8)
        except (json.JSONDecodeError, ValidationError) as e:
            last = f"{label}: invalid output ({type(e).__name__})"
            log.warning("LLM attempt %d failed (%s)", attempts, last)
    raise LLMError(f"LLM call failed after {attempts} attempts: {last}")

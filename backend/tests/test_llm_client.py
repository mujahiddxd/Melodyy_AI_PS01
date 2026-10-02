"""LLM client: key + model fallback, cooldown, validation, retry; re-rank id guard. No network."""
import pytest
from pydantic import BaseModel

from app.agents.matcher import rerank
from app.config import get_settings
from app.llm import client
from app.llm.client import LLMError, _Retryable, complete_json
from app.schemas.llm import RerankOut
from app.services.matcher import CatalogIndex, match
from tests.catalog import load_products


class Out(BaseModel):
    ok: bool


@pytest.fixture(autouse=True)
def live_settings(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "llm_mock", False)
    monkeypatch.setattr(s, "llm_provider", "gemini")
    monkeypatch.setattr(s, "llm_api_key", "key-1")
    monkeypatch.setattr(s, "llm_api_keys", "key-2, key-3")
    monkeypatch.setattr(s, "llm_model_text", "model-a")
    monkeypatch.setattr(s, "llm_model_fallbacks", "model-b")
    monkeypatch.setattr(client.time, "sleep", lambda *_: None)
    client._cooldown.clear()
    yield
    client._cooldown.clear()


def fake(monkeypatch, behaviour):
    calls = []

    def call(key, model, system, user, temperature):
        calls.append((key, model, temperature))
        return behaviour(key, model)

    monkeypatch.setitem(client._PROVIDERS, "gemini", call)
    return calls


def test_keys_are_listed_primary_first_and_deduplicated(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "llm_api_keys", " key-2,key-1,, key-3 ")
    assert s.llm_keys == ["key-1", "key-2", "key-3"]
    assert s.llm_models == ["model-a", "model-b"]


def test_a_rejected_key_falls_back_to_the_next_key(monkeypatch):
    def behaviour(key, model):
        if key == "key-1":
            raise _Retryable("http 403", client.COOLDOWN_AUTH_S)
        return '{"ok": true}'

    calls = fake(monkeypatch, behaviour)
    assert complete_json("s", "u", Out).ok is True
    assert [c[0] for c in calls] == ["key-1", "key-2"]
    # key-1 now cools down: the next call goes straight to key-2
    calls.clear()
    complete_json("s", "u", Out)
    assert [c[0] for c in calls] == ["key-2"]


def test_rate_limited_key_is_skipped_then_next_model_not_needed(monkeypatch):
    def behaviour(key, model):
        if key in ("key-1", "key-2"):
            raise _Retryable("http 429", client.COOLDOWN_RATE_S)
        return '{"ok": true}'

    calls = fake(monkeypatch, behaviour)
    assert complete_json("s", "u", Out).ok
    assert [c[0] for c in calls] == ["key-1", "key-2", "key-3"] and {c[1] for c in calls} == {"model-a"}


def test_overloaded_model_falls_back_to_the_next_model(monkeypatch):
    def behaviour(key, model):
        if model == "model-a":
            raise _Retryable("http 503", 0, model_level=True)
        return '{"ok": true}'

    calls = fake(monkeypatch, behaviour)
    assert complete_json("s", "u", Out).ok
    assert [(c[0], c[1]) for c in calls] == [("key-1", "model-a"), ("key-1", "model-b")]


def test_single_model_gets_one_retry_on_overload(monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_model_fallbacks", "")
    state = {"n": 0}

    def behaviour(key, model):
        state["n"] += 1
        if state["n"] == 1:
            raise _Retryable("http 503", 0, model_level=True)
        return '{"ok": true}'

    calls = fake(monkeypatch, behaviour)
    assert complete_json("s", "u", Out).ok and len(calls) == 2


def test_invalid_json_or_schema_is_retried_then_fails_safely(monkeypatch):
    calls = fake(monkeypatch, lambda k, m: "not json at all")
    with pytest.raises(LLMError):
        complete_json("s", "u", Out)
    assert len(calls) <= client.MAX_ATTEMPTS

    fake(monkeypatch, lambda k, m: '{"ok": "maybe"}')  # fails Pydantic validation
    with pytest.raises(LLMError):
        complete_json("s", "u", Out)


def test_json_in_a_code_fence_is_accepted(monkeypatch):
    fake(monkeypatch, lambda k, m: '```json\n{"ok": true}\n```')
    assert complete_json("s", "u", Out).ok


def test_all_keys_failing_raises_without_leaking_keys(monkeypatch):
    fake(monkeypatch, lambda k, m: (_ for _ in ()).throw(_Retryable("http 401", client.COOLDOWN_AUTH_S)))
    with pytest.raises(LLMError) as e:
        complete_json("s", "u", Out)
    assert "key-" not in str(e.value).replace("key#", "")


def test_no_key_configured(monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_api_key", "")
    monkeypatch.setattr(get_settings(), "llm_api_keys", "")
    with pytest.raises(LLMError):
        complete_json("s", "u", Out)


def test_temperature_is_passed_through(monkeypatch):
    calls = fake(monkeypatch, lambda k, m: '{"ok": true}')
    complete_json("s", "u", Out, temperature=0.3)
    complete_json("s", "u", Out)
    assert [c[2] for c in calls] == [0.3, 0.0]


# ---- re-rank: ids outside the candidate list are rejected ------------------------------------------------
@pytest.fixture
def rerank_candidates():
    index = CatalogIndex(load_products())
    res = match("suger", index)  # a typo that scores 80: between 60 and 85
    assert res.status == "rerank", res
    return res


def test_rerank_accepts_a_listed_id(monkeypatch, rerank_candidates):
    pid = rerank_candidates.candidates[0].product.id
    monkeypatch.setattr("app.agents.matcher.complete_json", lambda *a, **k: RerankOut(choice_product_id=pid, confidence=0.9, reason="ok"))
    out = rerank("suger", rerank_candidates)
    assert out.status == "matched" and out.product.id == pid


def test_rerank_rejects_an_id_that_was_not_offered(monkeypatch, rerank_candidates):
    monkeypatch.setattr("app.agents.matcher.complete_json", lambda *a, **k: RerankOut(choice_product_id=999999, confidence=0.99, reason="trust me"))
    out = rerank("suger", rerank_candidates)
    assert out.status == "ambiguous" and out.product is None  # the customer chooses; the foreign id is never used


def test_rerank_none_means_unmatched_and_failure_means_ask(monkeypatch, rerank_candidates):
    monkeypatch.setattr("app.agents.matcher.complete_json", lambda *a, **k: RerankOut(choice_product_id=None, confidence=0.1))
    assert rerank("suger", rerank_candidates).status == "unmatched"

    def boom(*a, **k):
        raise LLMError("down")

    monkeypatch.setattr("app.agents.matcher.complete_json", boom)
    assert rerank("suger", rerank_candidates).status == "ambiguous"


def test_mock_mode_never_calls_the_network(monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_mock", True)
    monkeypatch.setitem(client._PROVIDERS, "gemini", lambda *a: pytest.fail("network used in mock mode"))
    with pytest.raises(LLMError):
        complete_json("s", "u", Out, mock=("parser", "no such fixture"))


def test_throttled_model_is_skipped_on_the_next_call(monkeypatch):
    """429 on a key+model pair: later calls go straight to a model that works instead of retrying the throttled one."""
    def behaviour(key, model):
        if model == "model-a":
            raise _Retryable("http 429", client.COOLDOWN_RATE_S, scope="pair")
        return '{"ok": true}'

    calls = fake(monkeypatch, behaviour)
    assert complete_json("s", "u", Out).ok
    assert [c[1] for c in calls] == ["model-a", "model-a", "model-a", "model-b"]  # first call probes all 3 keys
    calls.clear()
    assert complete_json("s", "u", Out).ok
    assert [(c[0], c[1]) for c in calls] == [("key-1", "model-b")]


def test_a_rejected_key_is_skipped_for_every_model(monkeypatch):
    def behaviour(key, model):
        if key == "key-1":
            raise _Retryable("http 403", client.COOLDOWN_AUTH_S)
        return '{"ok": true}'

    calls = fake(monkeypatch, behaviour)
    complete_json("s", "u", Out)
    calls.clear()
    complete_json("s", "u", Out)
    assert {c[0] for c in calls} == {"key-2"}

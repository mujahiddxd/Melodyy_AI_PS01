"""Every test runs with LLM_MOCK=true (canned parser output), whatever backend/.env says: tests never call a real LLM."""
import pytest

from app.config import get_settings


@pytest.fixture(autouse=True)
def _force_llm_mock(monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_mock", True)

from functools import lru_cache
from pathlib import Path

_DIR = Path(__file__).resolve().parent


@lru_cache
def load_prompt(name: str) -> str:
    """Prompt text from llm/prompts/<name>.md (intake, parser, clarifier, rerank)."""
    return (_DIR / f"{name}.md").read_text(encoding="utf-8")

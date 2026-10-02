"""Pydantic contracts for LLM output (Appendix B). LLM output is untrusted: nothing here carries prices, stock or
product ids except the re-rank choice, which is checked against the candidate ids that were sent in."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Language = Literal["hinglish", "hindi", "marathi", "english"]
Script = Literal["latin", "devanagari"]
Intent = Literal[
    "new_order", "add_items", "remove_items", "change_quantity", "answer_clarification", "confirm", "cancel",
    "repeat_last_order", "status_query", "availability_query", "gibberish", "other",
]


def _str_or_none(v):
    if v is None:
        return None
    s = str(v).strip()
    return s or None


class IntakeOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    language: Language
    script: Script
    category: Literal["order", "gibberish", "other"]


class ParsedItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    raw_text: str = ""
    name_guess: str = ""
    brand_guess: str | None = None
    quantity_value: float | None = None
    quantity_text: str | None = None
    unit_text: str | None = None
    is_vague: bool = False
    refers_to_history: bool = False
    target_item_ref: str | int | None = None
    source_span: list[int] | None = None

    @field_validator("brand_guess", "quantity_text", "unit_text", mode="before")
    @classmethod
    def _coerce(cls, v):
        return _str_or_none(v)

    @field_validator("name_guess", "raw_text", mode="before")
    @classmethod
    def _text(cls, v):
        return "" if v is None else str(v).strip()


class ParserOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    language: Language
    script: Script
    intent: Intent
    items: list[ParsedItem] = Field(default_factory=list)
    delivery_time_text: str | None = None
    notes: str | None = None

    @field_validator("delivery_time_text", "notes", mode="before")
    @classmethod
    def _coerce(cls, v):
        return _str_or_none(v)


class RerankOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    choice_product_id: int | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason: str = ""


class ClarifierOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message: str = Field(min_length=1, max_length=800)

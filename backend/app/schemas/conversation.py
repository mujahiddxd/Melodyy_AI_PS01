from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.common import Money, Qty


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    shop_id: int
    language: str | None
    script: str | None
    status: str
    created_at: datetime


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: int
    sender: str
    type: str
    content: str
    media_url: str | None
    meta: dict | None
    created_at: datetime


class AgentRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    agent: str
    status: str
    input: dict | list | None
    output: dict | list | None
    error: str | None
    started_at: datetime
    duration_ms: int | None


class ProductSummary(BaseModel):
    """The product an order line points at (from the database)."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    brand: str | None
    sell_mode: str
    pack_size: Qty
    pack_unit: str
    price: Money
    stock_status: str


class OrderItemOut(BaseModel):
    id: int
    product_id: int | None
    product_name: str | None
    raw_text: str
    name_guess: str
    quantity_value: Qty | None
    unit: str | None
    normalized_qty: Qty | None
    product_qty: Qty | None
    unit_price_snapshot: Money | None
    line_total: Money | None
    confidence: float
    status: str
    candidates: list[dict]
    source_span: list[int] | None
    parent_item_id: int | None = None
    product: ProductSummary | None = None


class ClarificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_item_id: int
    kind: str
    question: str
    options: list[dict]
    answer: dict | None
    resolved_at: datetime | None


class OrderOut(BaseModel):
    id: int
    order_no: int
    shop_id: int
    conversation_id: int
    status: str
    requires_reapproval: bool
    items: list[OrderItemOut]
    clarifications: list[ClarificationOut]
    subtotal: Money
    discount: Money
    delivery_fee: Money
    total: Money
    delivery_address_text: str | None
    delivery_lat: float | None
    delivery_lng: float | None
    distance_km: float | None
    requested_delivery_text: str | None
    requested_delivery_at: datetime | None
    payment_method: str | None
    payment_status: str | None
    quoted_at: datetime | None
    confirmed_at: datetime | None
    created_at: datetime


class MessageIn(BaseModel):
    type: Literal["text"] = "text"
    content: str


class AnswerIn(BaseModel):
    option_product_id: int | None = None
    text: str | None = None


class CreateConversationOut(BaseModel):
    conversation: ConversationOut
    guest_session: str | None
    messages: list[MessageOut]
    order: OrderOut | None
    llm_mock: bool


class ConversationStateOut(BaseModel):
    conversation: ConversationOut
    messages: list[MessageOut]
    order: OrderOut | None
    agent_runs: list[AgentRunOut]
    llm_mock: bool


class ChatResponse(BaseModel):
    messages: list[MessageOut]
    order: OrderOut | None
    agent_runs: list[AgentRunOut]


class ClaimOut(BaseModel):
    conversation_id: int
    customer_id: int

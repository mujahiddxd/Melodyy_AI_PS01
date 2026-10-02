from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, DateTime, Enum, Float, ForeignKey, Index, Integer, Numeric, String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

CONVERSATION_STATUSES = ("open", "closed")
MESSAGE_SENDERS = ("customer", "bot", "shopkeeper", "system")
MESSAGE_TYPES = ("text", "audio", "image", "system", "bill")
# Every status of the order state machine (plan 1.2), even those later stages use.
ORDER_STATUSES = (
    "draft", "needs_clarification", "awaiting_confirmation", "confirmed",
    "packing", "out_for_delivery", "delivered", "cancelled",
)
PAYMENT_METHODS = ("cod", "upi", "razorpay")
PAYMENT_STATUSES = ("pending", "paid", "cod")
ITEM_STATUSES = (
    "matched", "ambiguous", "out_of_stock", "unmatched", "vague_qty",
    "removed", "substituted", "pending_amendment",
)
CLARIFICATION_KINDS = (
    "ambiguous_product", "pack_size", "out_of_stock", "unmatched", "vague_qty", "unusual_qty", "price_change",
)
STATUS_ACTORS = ("customer", "shopkeeper", "system")
AGENT_NAMES = ("intake", "parser", "matcher", "inventory", "clarifier", "billing", "messaging", "stt", "ocr", "explainer")
AGENT_STATUSES = ("running", "success", "error", "skipped")

# Order statuses in which the customer can still change the draft.
OPEN_ORDER_STATUSES = ("draft", "needs_clarification", "awaiting_confirmation")


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"), index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), index=True)
    # sha256 of the X-Guest-Session token. The token itself is only ever returned once, at creation.
    guest_session_id: Mapped[str | None] = mapped_column(String(64), index=True)
    language: Mapped[str | None] = mapped_column(String(16))
    script: Mapped[str | None] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(Enum(*CONVERSATION_STATUSES, name="conversation_status"), default="open", server_default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_conversation_id_id", "conversation_id", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"))
    sender: Mapped[str] = mapped_column(Enum(*MESSAGE_SENDERS, name="message_sender"))
    type: Mapped[str] = mapped_column(Enum(*MESSAGE_TYPES, name="message_type"), default="text", server_default="text")
    content: Mapped[str] = mapped_column(Text)
    media_url: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"), index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"))
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), index=True)
    status: Mapped[str] = mapped_column(Enum(*ORDER_STATUSES, name="order_status"), default="draft", server_default="draft")
    requires_reapproval: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    address_id: Mapped[int | None] = mapped_column(ForeignKey("customer_addresses.id"))
    delivery_address_text: Mapped[str | None] = mapped_column(Text)
    delivery_lat: Mapped[float | None] = mapped_column(Float)
    delivery_lng: Mapped[float | None] = mapped_column(Float)
    distance_km: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    requested_delivery_text: Mapped[str | None] = mapped_column(Text)
    requested_delivery_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    subtotal: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, server_default="0")
    discount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, server_default="0")
    delivery_fee: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, server_default="0")
    total: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, server_default="0")
    payment_method: Mapped[str | None] = mapped_column(Enum(*PAYMENT_METHODS, name="payment_method"))
    payment_status: Mapped[str | None] = mapped_column(Enum(*PAYMENT_STATUSES, name="payment_status"))
    quoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"))
    raw_text: Mapped[str] = mapped_column(Text)
    name_guess: Mapped[str] = mapped_column(String(160))
    quantity_value: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    unit: Mapped[str | None] = mapped_column(String(16))
    normalized_qty: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    product_qty: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))  # packs, or base units if loose
    unit_price_snapshot: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))  # set by the quote (Stage 4)
    line_total: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    confidence: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=0, server_default="0")
    status: Mapped[str] = mapped_column(Enum(*ITEM_STATUSES, name="order_item_status"))
    candidates: Mapped[list | None] = mapped_column(JSONB)
    source_span: Mapped[list | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Clarification(Base):
    __tablename__ = "clarifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    order_item_id: Mapped[int] = mapped_column(ForeignKey("order_items.id"))
    kind: Mapped[str] = mapped_column(Enum(*CLARIFICATION_KINDS, name="clarification_kind"))
    question: Mapped[str] = mapped_column(Text)
    options: Mapped[list | None] = mapped_column(JSONB)
    answer: Mapped[dict | None] = mapped_column(JSONB)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentRun(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (Index("ix_agent_runs_conversation_id_id", "conversation_id", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"))
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"))
    message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id"))
    agent: Mapped[str] = mapped_column(Enum(*AGENT_NAMES, name="agent_name"))
    status: Mapped[str] = mapped_column(Enum(*AGENT_STATUSES, name="agent_status"))
    input: Mapped[dict | None] = mapped_column(JSONB)
    output: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    duration_ms: Mapped[int | None] = mapped_column(Integer)


class OrderStatusEvent(Base):
    """One row per order state transition (plan 1.2). Written only by services/order_state_machine.py."""
    __tablename__ = "order_status_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    from_status: Mapped[str | None] = mapped_column(Enum(*ORDER_STATUSES, name="order_status", create_type=False))
    to_status: Mapped[str] = mapped_column(Enum(*ORDER_STATUSES, name="order_status", create_type=False))
    actor: Mapped[str] = mapped_column(Enum(*STATUS_ACTORS, name="status_actor"))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

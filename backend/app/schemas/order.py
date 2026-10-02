from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Money
from app.schemas.conversation import AgentRunOut, MessageOut, OrderOut

OrderStatusName = Literal[
    "draft", "needs_clarification", "awaiting_confirmation", "confirmed", "packing", "out_for_delivery",
    "delivered", "cancelled",
]


class BillLine(BaseModel):
    item_id: int
    product_id: int
    name: str
    qty: str
    unit: str
    qty_label: str
    unit_price: str
    line_total: str


class Bill(BaseModel):
    order_id: int
    order_no: int
    lines: list[BillLine]
    subtotal: str
    discount: str
    delivery_fee: str
    total: str
    payment_method: str | None
    requires_reapproval: bool
    quoted_at: str | None


class ConfirmIn(BaseModel):
    address_id: int
    payment_method: Literal["cod"] = "cod"  # upi / razorpay arrive in Stage 7


class CancelIn(BaseModel):
    reason: str | None = Field(default=None, max_length=300)


class StatusIn(BaseModel):
    to: OrderStatusName
    note: str | None = Field(default=None, max_length=300)


class StatusEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    from_status: str | None
    to_status: str
    actor: str
    note: str | None
    created_at: datetime


class QuoteOut(BaseModel):
    order: OrderOut
    bill: Bill
    message: MessageOut


class ConfirmOut(BaseModel):
    order: OrderOut
    message: str
    newly_confirmed: bool


class OrderEnvelope(BaseModel):
    order: OrderOut


class CustomerOrderOut(BaseModel):
    order: OrderOut
    timeline: list[StatusEventOut]


# ---- owner board ----------------------------------------------------------------------------------------
class OwnerOrderCard(BaseModel):
    id: int
    order_no: int
    status: str
    customer_phone_masked: str | None
    item_count: int
    total: Money
    payment_method: str | None
    payment_status: str | None
    requested_delivery_text: str | None
    requested_delivery_at: datetime | None
    has_problem: bool
    created_at: datetime
    updated_at: datetime


class OwnerOrderList(BaseModel):
    items: list[OwnerOrderCard]


class OwnerCustomer(BaseModel):
    phone_masked: str | None


class OwnerShopPin(BaseModel):
    name: str
    lat: float | None
    lng: float | None


class OwnerOrderDetail(BaseModel):
    order: OrderOut
    customer: OwnerCustomer
    shop: OwnerShopPin
    messages: list[MessageOut]
    bill: Bill | None
    problems: list[str]
    allowed_next: list[str]
    timeline: list[StatusEventOut]
    agent_runs: list[AgentRunOut]


class DeliveryNoteItem(BaseModel):
    name: str
    qty: str
    unit: str
    qty_label: str
    unit_price: str
    line_total: str


class DeliveryNote(BaseModel):
    order_no: int
    shop_name: str
    customer_phone: str | None
    delivery_address_text: str | None
    delivery_lat: float | None
    delivery_lng: float | None
    requested_delivery_text: str | None
    requested_delivery_at: datetime | None
    items: list[DeliveryNoteItem]
    subtotal: str
    delivery_fee: str
    total: str
    payment_method: str | None
    payment_status: str | None
    created_at: datetime

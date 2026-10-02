import secrets

from fastapi import APIRouter, Depends, Header
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.agents import orchestrator
from app.config import get_settings
from app.db import get_db
from app.deps import get_conversation, get_current_customer, hash_guest_session, optional_customer
from app.errors import api_error
from app.models import Clarification, Conversation, Customer, Message, Order, Shop
from app.models.conversation import OPEN_ORDER_STATUSES
from app.schemas.conversation import (
    AnswerIn, ChatResponse, ClaimOut, ConversationOut, ConversationStateOut, CreateConversationOut, MessageIn,
)
from app.services import orders as orders_svc

router = APIRouter(tags=["conversations"])
MAX_MESSAGE_CHARS = 1000


def _shop_of(db: Session, conv: Conversation) -> Shop:
    shop = db.get(Shop, conv.shop_id)
    if shop is None:
        raise api_error(404, "NOT_FOUND", "Shop not found.")
    return shop


def _chat_response(db: Session, result: orchestrator.ChatResult) -> ChatResponse:
    return ChatResponse(
        messages=orders_svc.messages_out(result.messages),
        order=orders_svc.serialize_order(db, result.order),
        agent_runs=orders_svc.runs_out(result.runs),
    )


def _respond(db: Session, result: orchestrator.ChatResult) -> ChatResponse:
    """200 with the new messages, or 502 LLM_FAILED carrying the stored safe failure message so the chat can show it."""
    body = _chat_response(db, result)
    if result.failed:
        raise api_error(
            502, "LLM_FAILED", "The AI helper is unavailable right now. Please try again.",
            messages=[m.model_dump(mode="json") for m in body.messages],
            agent_runs=[r.model_dump(mode="json") for r in body.agent_runs],
        )
    return body


@router.post("/shops/{slug}/conversations", response_model=CreateConversationOut, status_code=201)
def create_conversation(
    slug: str, db: Session = Depends(get_db), customer: Customer | None = Depends(optional_customer),
):
    shop = db.scalar(select(Shop).where(Shop.slug == slug))
    if shop is None:
        raise api_error(404, "NOT_FOUND", "Shop not found.")
    token = None if customer else f"gs_{secrets.token_urlsafe(24)}"
    conv = Conversation(
        shop_id=shop.id, customer_id=customer.id if customer else None,
        guest_session_id=hash_guest_session(token) if token else None,
    )
    db.add(conv)
    db.commit()
    return CreateConversationOut(
        conversation=ConversationOut.model_validate(conv), guest_session=token, messages=[], order=None,
        llm_mock=get_settings().llm_mock,
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationStateOut)
def read_conversation(conv: Conversation = Depends(get_conversation), db: Session = Depends(get_db)):
    msgs = list(db.scalars(select(Message).where(Message.conversation_id == conv.id).order_by(Message.id)))
    return ConversationStateOut(
        conversation=ConversationOut.model_validate(conv),
        messages=orders_svc.messages_out(msgs),
        order=orders_svc.serialize_order(db, orders_svc.latest_order(db, conv.id)),
        agent_runs=orders_svc.runs_out(orders_svc.latest_agent_runs(db, conv.id)),
        llm_mock=get_settings().llm_mock,
    )


@router.post("/conversations/{conversation_id}/claim", response_model=ClaimOut)
def claim_conversation(
    conversation_id: int,
    customer: Customer = Depends(get_current_customer),
    x_guest_session: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """Attach a guest conversation (and its orders) to the customer who just verified their phone."""
    conv = db.get(Conversation, conversation_id)
    if conv is None:
        raise api_error(404, "NOT_FOUND", "Conversation not found.")
    if conv.customer_id == customer.id:
        return ClaimOut(conversation_id=conv.id, customer_id=customer.id)  # idempotent
    guest_ok = bool(x_guest_session) and conv.guest_session_id == hash_guest_session(x_guest_session or "")
    if conv.customer_id is not None or not guest_ok:
        raise api_error(403, "FORBIDDEN", "This conversation belongs to someone else.")
    conv.customer_id = customer.id
    db.execute(update(Order).where(Order.conversation_id == conv.id, Order.customer_id.is_(None)).values(customer_id=customer.id))
    db.commit()
    return ClaimOut(conversation_id=conv.id, customer_id=customer.id)


@router.post("/conversations/{conversation_id}/messages", response_model=ChatResponse)
def send_message(body: MessageIn, conv: Conversation = Depends(get_conversation), db: Session = Depends(get_db)):
    if len(body.content) > MAX_MESSAGE_CHARS:
        raise api_error(422, "MESSAGE_TOO_LONG", f"Messages can be at most {MAX_MESSAGE_CHARS} characters.")
    text = body.content.strip()
    if not text:
        raise api_error(422, "VALIDATION_ERROR", "Message is empty.")
    shop = _shop_of(db, conv)
    return _respond(db, orchestrator.handle_text_message(db, conv, shop, text))


@router.post("/conversations/{conversation_id}/clarifications/{clarification_id}/answer", response_model=ChatResponse)
def answer_clarification(
    clarification_id: int, body: AnswerIn,
    conv: Conversation = Depends(get_conversation), db: Session = Depends(get_db),
):
    clar = db.get(Clarification, clarification_id)
    order = db.get(Order, clar.order_id) if clar else None
    if clar is None or order is None or order.conversation_id != conv.id:
        raise api_error(404, "NOT_FOUND", "Question not found.")
    if clar.resolved_at is not None:
        raise api_error(409, "CONFLICT", "This question was already answered.")
    if order.status not in OPEN_ORDER_STATUSES:
        raise api_error(409, "INVALID_TRANSITION", "This order can no longer be changed.")

    text = (body.text or "").strip() or None
    if (body.option_product_id is None) == (text is None):
        raise api_error(422, "VALIDATION_ERROR", "Send either option_product_id or text.")
    if body.option_product_id is not None and body.option_product_id not in {o["product_id"] for o in (clar.options or [])}:
        raise api_error(422, "VALIDATION_ERROR", "That option was not offered for this question.")
    if text is not None and len(text) > MAX_MESSAGE_CHARS:
        raise api_error(422, "MESSAGE_TOO_LONG", f"Messages can be at most {MAX_MESSAGE_CHARS} characters.")

    shop = _shop_of(db, conv)
    return _respond(db, orchestrator.handle_clarification_answer(db, conv, shop, clar, body.option_product_id, text))

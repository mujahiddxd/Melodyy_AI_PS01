import hashlib

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import api_error
from app.models import Conversation, Customer, Shop, Shopkeeper
from app.security import decode_token

_bearer = HTTPBearer(auto_error=False)


def _unauthorized():
    exc = api_error(401, "UNAUTHORIZED", "Please log in again.")
    exc.headers = {"WWW-Authenticate": "Bearer"}
    return exc


def get_current_owner(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> Shopkeeper:
    """401 without a valid token; 403 for a valid token of another role (e.g. a customer)."""
    if creds is None:
        raise _unauthorized()
    claims = decode_token(creds.credentials)
    if not claims or not str(claims.get("sub", "")).isdigit():
        raise _unauthorized()
    if claims.get("role") != "shopkeeper":
        raise api_error(403, "FORBIDDEN", "This area is for shopkeepers only.")
    owner = db.get(Shopkeeper, int(claims["sub"]))
    if owner is None:
        raise _unauthorized()
    return owner


def find_owner_shop(db: Session, owner: Shopkeeper) -> Shop | None:
    return db.scalar(select(Shop).where(Shop.owner_id == owner.id).order_by(Shop.id))


def get_owner_shop(owner: Shopkeeper = Depends(get_current_owner), db: Session = Depends(get_db)) -> Shop:
    shop = find_owner_shop(db, owner)
    if shop is None:
        raise api_error(404, "NOT_FOUND", "Set up your shop first.")
    return shop


def get_current_customer(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> Customer:
    """Only an OTP-verified customer token passes. 401 without one; 403 for a token of another role."""
    if creds is None:
        raise _unauthorized()
    claims = decode_token(creds.credentials)
    if not claims or not str(claims.get("sub", "")).isdigit():
        raise _unauthorized()
    if claims.get("role") != "customer":
        raise api_error(403, "FORBIDDEN", "This area is for verified customers only.")
    customer = db.get(Customer, int(claims["sub"]))
    if customer is None or customer.verified_at is None:
        raise _unauthorized()
    return customer


def hash_guest_session(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def optional_customer(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> Customer | None:
    """A verified customer if a valid customer token is sent, otherwise None (guests are allowed to chat)."""
    if creds is None:
        return None
    claims = decode_token(creds.credentials)
    if not claims or claims.get("role") != "customer" or not str(claims.get("sub", "")).isdigit():
        return None
    customer = db.get(Customer, int(claims["sub"]))
    return customer if customer is not None and customer.verified_at is not None else None


def get_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    customer: Customer | None = Depends(optional_customer),
    x_guest_session: str | None = Header(default=None),
) -> Conversation:
    """The conversation, for its owner only: the guest session that created it, or the customer it belongs to.
    401 without any credential, 404 unknown id, 403 for someone else's conversation."""
    if customer is None and not x_guest_session:
        raise _unauthorized()
    conv = db.get(Conversation, conversation_id)
    if conv is None:
        raise api_error(404, "NOT_FOUND", "Conversation not found.")
    owns_as_customer = customer is not None and conv.customer_id == customer.id
    owns_as_guest = bool(x_guest_session) and conv.guest_session_id == hash_guest_session(x_guest_session or "")
    if not (owns_as_customer or owns_as_guest):
        raise api_error(403, "FORBIDDEN", "This conversation belongs to someone else.")
    return conv

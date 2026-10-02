from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import api_error
from app.models import Shop, Shopkeeper
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

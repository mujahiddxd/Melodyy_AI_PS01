from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import find_owner_shop
from app.errors import api_error
from app.models import Shopkeeper
from app.schemas.auth import AuthOut, OwnerLogin, OwnerSignup, normalize_phone
from app.security import create_access_token, hash_password, verify_password
from app.services.shops import is_configured

router = APIRouter(prefix="/auth/owner", tags=["auth"])


@router.post("/signup", response_model=AuthOut, status_code=201)
def signup(body: OwnerSignup, db: Session = Depends(get_db)):
    taken = db.scalar(
        select(Shopkeeper.id).where(
            (Shopkeeper.email == body.email) if body.email else (Shopkeeper.phone == body.phone)
        )
    )
    if taken is None and body.email and body.phone:
        taken = db.scalar(select(Shopkeeper.id).where(Shopkeeper.phone == body.phone))
    if taken is not None:
        raise api_error(409, "CONFLICT", "An account with this phone or email already exists.")

    owner = Shopkeeper(
        name=body.name, email=body.email, phone=body.phone, password_hash=hash_password(body.password)
    )
    db.add(owner)
    try:
        db.commit()
    except IntegrityError:  # lost a race with a parallel signup
        db.rollback()
        raise api_error(409, "CONFLICT", "An account with this phone or email already exists.")
    return AuthOut(access_token=create_access_token(owner.id, "shopkeeper"), shop_id=None, has_shop=False)


@router.post("/login", response_model=AuthOut)
def login(body: OwnerLogin, db: Session = Depends(get_db)):
    ident = body.identifier
    if "@" in ident:
        owner = db.scalar(select(Shopkeeper).where(Shopkeeper.email == ident.lower()))
    else:
        owner = db.scalar(select(Shopkeeper).where(Shopkeeper.phone == normalize_phone(ident)))
    if not verify_password(body.password, owner.password_hash if owner else None):
        raise HTTPException(status_code=401, detail="Incorrect email/phone or password.")
    shop = find_owner_shop(db, owner)
    return AuthOut(
        access_token=create_access_token(owner.id, "shopkeeper", shop.id if shop else None),
        shop_id=shop.id if shop else None,
        has_shop=bool(shop and is_configured(shop)),
    )

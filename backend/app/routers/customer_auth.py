import logging
import math
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import api_error
from app.models import Customer, OtpRequest
from app.schemas.auth import PHONE_RE, normalize_phone
from app.schemas.customer import (
    CustomerAuthOut, CustomerOut, DemoInboxOut, DemoMessage, OtpRequestIn, OtpRequestOut, OtpVerifyIn,
)
from app.security import create_access_token
from app.services import otp

log = logging.getLogger("hod.customer_auth")
router = APIRouter(prefix="/auth/customer", tags=["customer auth"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _lock_phone(db: Session, phone: str) -> None:
    """Serialise OTP calls per phone (released at commit/rollback) so parallel requests can't beat the limits."""
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"otp:{phone}"})


@router.post("/otp/request", response_model=OtpRequestOut, status_code=202)
def request_otp(body: OtpRequestIn, db: Session = Depends(get_db)):
    phone, now = body.phone, _now()
    _lock_phone(db, phone)

    recent = db.scalars(
        select(OtpRequest)
        .where(OtpRequest.phone == phone, OtpRequest.created_at > now - timedelta(seconds=otp.REQUEST_WINDOW_SECONDS))
        .order_by(OtpRequest.created_at.desc())
    ).all()
    if len(recent) >= otp.MAX_REQUESTS:
        wait = math.ceil((recent[-1].created_at + timedelta(seconds=otp.REQUEST_WINDOW_SECONDS) - now).total_seconds())
        raise api_error(
            429, "OTP_RATE_LIMITED",
            f"Too many codes requested. Try again in {max(wait, 1)} seconds.", retry_after_seconds=max(wait, 1),
        )
    if recent:
        wait = math.ceil((recent[0].created_at + timedelta(seconds=otp.RESEND_AFTER_SECONDS) - now).total_seconds())
        if wait > 0:
            raise api_error(
                429, "OTP_RATE_LIMITED", f"Please wait {wait} seconds before asking for another code.",
                retry_after_seconds=wait,
            )

    code = otp.generate_code()
    # a newer code replaces any older unused one, so only the latest code can ever verify
    db.execute(update(OtpRequest).where(OtpRequest.phone == phone, OtpRequest.consumed_at.is_(None)).values(consumed_at=now))
    row = OtpRequest(
        phone=phone,
        code_hash=otp.hash_code(code, phone),
        expires_at=now + timedelta(seconds=otp.OTP_TTL_SECONDS),
        created_at=now,
    )
    db.add(row)
    db.flush()
    provider = otp.get_provider()
    try:
        provider.send(phone, code, row.id)
    except Exception as e:
        db.rollback()  # a failed send doesn't use up one of the 3 requests
        log.error("OTP send via %s failed: %s", provider.name, e)
        raise api_error(502, "SMS_FAILED", "Could not send the code right now. Please try again.")
    db.commit()
    return OtpRequestOut(
        expires_in_seconds=otp.OTP_TTL_SECONDS, resend_after_seconds=otp.RESEND_AFTER_SECONDS, provider=provider.name
    )


@router.post("/otp/verify", response_model=CustomerAuthOut)
def verify_otp(body: OtpVerifyIn, db: Session = Depends(get_db)):
    phone, now = body.phone, _now()
    _lock_phone(db, phone)

    row = db.scalar(select(OtpRequest).where(OtpRequest.phone == phone).order_by(OtpRequest.id.desc()))
    if row is None or row.consumed_at is not None or row.expires_at <= now:
        raise api_error(400, "OTP_EXPIRED", "This code has expired or was already used. Request a new one.")
    if row.attempts >= otp.MAX_ATTEMPTS:
        raise api_error(
            429, "OTP_TOO_MANY_ATTEMPTS", "Too many wrong attempts. Request a new code.", attempts_left=0
        )

    row.attempts += 1
    if not otp.code_matches(body.code, phone, row.code_hash):
        left = otp.MAX_ATTEMPTS - row.attempts
        db.commit()  # the failed attempt must be counted
        raise api_error(
            400, "OTP_INVALID",
            "Wrong code. Check the code and try again." if left else "Wrong code. No attempts left, request a new code.",
            attempts_left=left,
        )

    row.consumed_at = now
    customer = db.scalar(select(Customer).where(Customer.phone == phone))
    if customer is None:
        customer = Customer(phone=phone)
        db.add(customer)
    if customer.verified_at is None:
        customer.verified_at = now
    db.commit()
    db.refresh(customer)
    return CustomerAuthOut(
        access_token=create_access_token(customer.id, "customer"), customer=CustomerOut.model_validate(customer)
    )


@router.get("/otp/demo-inbox", response_model=DemoInboxOut)
def demo_inbox(phone: str = Query(max_length=20), db: Session = Depends(get_db)):
    """Mock mode only: shows the latest unexpired, unconsumed code for a phone. 404 for any real provider."""
    if not otp.is_mock_mode():
        raise api_error(404, "NOT_FOUND", "Not found.")
    phone = normalize_phone(phone)
    if not PHONE_RE.match(phone):
        raise api_error(422, "VALIDATION_ERROR", "Enter a valid 10-digit mobile number.")
    latest = otp.mock_latest(phone)
    if latest:
        row = db.get(OtpRequest, latest[0])
        if row and row.consumed_at is None and row.expires_at > _now():
            return DemoInboxOut(
                messages=[DemoMessage(phone=phone, code=latest[1], created_at=row.created_at, expires_at=row.expires_at)]
            )
    return DemoInboxOut(messages=[])

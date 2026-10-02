"""Customer OTP, addresses and delivery-check API tests. Uses the dev Postgres; cleans up after itself."""
import random
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models import Customer, CustomerAddress, OtpRequest
from app.security import create_access_token
from app.services import otp

client = TestClient(app)


@pytest.fixture(autouse=True)
def mock_mode(monkeypatch):
    monkeypatch.setattr(get_settings(), "otp_provider", "mock")


@pytest.fixture
def phone():
    p = f"9{random.randint(100000000, 999999999)}"
    yield p
    with SessionLocal() as db:
        cid = select(Customer.id).where(Customer.phone == p)
        db.execute(delete(CustomerAddress).where(CustomerAddress.customer_id.in_(cid)))
        db.execute(delete(Customer).where(Customer.phone == p))
        db.execute(delete(OtpRequest).where(OtpRequest.phone == p))
        db.commit()


def request(phone):
    return client.post("/auth/customer/otp/request", json={"phone": phone})


def inbox_code(phone):
    msgs = client.get("/auth/customer/otp/demo-inbox", params={"phone": phone}).json()["messages"]
    return msgs[0]["code"] if msgs else None


def verify(phone, code):
    return client.post("/auth/customer/otp/verify", json={"phone": phone, "code": code})


def age(phone, seconds):
    """Pretend this phone's codes were requested `seconds` earlier."""
    with SessionLocal() as db:
        db.execute(
            update(OtpRequest).where(OtpRequest.phone == phone)
            .values(created_at=OtpRequest.created_at - timedelta(seconds=seconds))
        )
        db.commit()


def wrong(code):
    return f"{(int(code) + 1) % 1_000_000:06d}"


def test_happy_path_and_hash_only(phone):
    r = request(phone)
    assert r.status_code == 202, r.text
    assert r.json() == {"status": "sent", "expires_in_seconds": 300, "resend_after_seconds": 30, "provider": "mock"}
    code = inbox_code(phone)
    assert code and len(code) == 6 and code.isdigit()

    with SessionLocal() as db:
        row = db.scalar(select(OtpRequest).where(OtpRequest.phone == phone))
        assert code not in row.code_hash and row.code_hash == otp.hash_code(code, phone) and len(row.code_hash) == 64
        assert (row.expires_at - row.created_at) == timedelta(minutes=5)

    r = verify(phone, code)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["customer"]["phone"] == phone and body["token_type"] == "bearer"
    h = {"Authorization": f"Bearer {body['access_token']}"}
    assert client.get("/customer/me", headers=h).json()["phone"] == phone
    with SessionLocal() as db:
        assert db.scalar(select(Customer).where(Customer.phone == phone)).verified_at is not None

    # consumed: same code can't be reused, and the inbox no longer shows it
    assert verify(phone, code).json()["detail"]["code"] == "OTP_EXPIRED"
    assert inbox_code(phone) is None


def test_plus91_prefix_accepted(phone):
    assert request(f"+91 {phone}").status_code == 202
    assert inbox_code(phone)


@pytest.mark.parametrize("bad", ["12345", "5876543210", "98765432101", "abcdefghij", ""])
def test_invalid_phone(bad):
    assert client.post("/auth/customer/otp/request", json={"phone": bad}).status_code == 422


def test_wrong_code_and_sixth_attempt_blocked(phone):
    request(phone)
    code = inbox_code(phone)
    for left in [4, 3, 2, 1, 0]:
        r = verify(phone, wrong(code))
        assert r.status_code == 400 and r.json()["detail"]["code"] == "OTP_INVALID"
        assert r.json()["detail"]["attempts_left"] == left
    r = verify(phone, code)  # 6th attempt, even with the right code
    assert r.status_code == 429 and r.json()["detail"]["code"] == "OTP_TOO_MANY_ATTEMPTS"


def test_expired_code(phone):
    request(phone)
    code = inbox_code(phone)
    with SessionLocal() as db:
        db.execute(update(OtpRequest).where(OtpRequest.phone == phone).values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
        db.commit()
    r = verify(phone, code)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "OTP_EXPIRED"
    assert inbox_code(phone) is None


def test_resend_cooldown_and_rate_limit(phone):
    assert request(phone).status_code == 202
    r = request(phone)  # within 30 s
    assert r.status_code == 429 and r.json()["detail"]["code"] == "OTP_RATE_LIMITED"
    assert 0 < r.json()["detail"]["retry_after_seconds"] <= 30
    age(phone, 31)
    assert request(phone).status_code == 202
    age(phone, 31)
    assert request(phone).status_code == 202
    age(phone, 31)
    r = request(phone)  # 4th within 10 minutes
    assert r.status_code == 429 and r.json()["detail"]["code"] == "OTP_RATE_LIMITED"
    age(phone, 600)  # window passed
    assert request(phone).status_code == 202


def test_old_code_invalid_after_new_request(phone):
    request(phone)
    old = inbox_code(phone)
    age(phone, 31)
    request(phone)
    new = inbox_code(phone)
    if old != new:
        assert verify(phone, old).json()["detail"]["code"] == "OTP_INVALID"
    assert verify(phone, new).status_code == 200


def test_demo_inbox_only_in_mock_mode(phone, monkeypatch):
    request(phone)
    monkeypatch.setattr(get_settings(), "otp_provider", "msg91")
    assert client.get("/auth/customer/otp/demo-inbox", params={"phone": phone}).status_code == 404


def test_send_failure_does_not_count(phone, monkeypatch):
    monkeypatch.setattr(get_settings(), "otp_provider", "msg91")
    monkeypatch.setattr(get_settings(), "msg91_template_id", "")
    r = request(phone)
    assert r.status_code == 502 and r.json()["detail"]["code"] == "SMS_FAILED"
    with SessionLocal() as db:
        assert db.scalar(select(OtpRequest).where(OtpRequest.phone == phone)) is None


def customer_headers(phone):
    request(phone)
    tok = verify(phone, inbox_code(phone)).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def test_addresses_require_customer_and_are_private(phone):
    assert client.get("/customer/addresses").status_code == 401
    owner_tok = create_access_token(1, "shopkeeper")
    assert client.get("/customer/addresses", headers={"Authorization": f"Bearer {owner_tok}"}).status_code == 403

    h = customer_headers(phone)
    assert client.get("/customer/addresses", headers=h).json() == {"items": []}
    body = {"label": "Home", "address_text": "Flat 12, near Karve Nagar bus stop", "lat": 18.5, "lng": 73.81}
    r = client.post("/customer/addresses", json=body, headers=h)
    assert r.status_code == 201 and r.json()["label"] == "Home"
    assert client.post("/customer/addresses", json={**body, "label": "Gym"}, headers=h).status_code == 422
    assert client.post("/customer/addresses", json={**body, "address_text": ""}, headers=h).status_code == 422
    assert len(client.get("/customer/addresses", headers=h).json()["items"]) == 1

    other = f"8{random.randint(100000000, 999999999)}"
    try:
        h2 = customer_headers(other)
        assert client.get("/customer/addresses", headers=h2).json() == {"items": []}
    finally:
        with SessionLocal() as db:
            db.execute(delete(Customer).where(Customer.phone == other))
            db.execute(delete(OtpRequest).where(OtpRequest.phone == other))
            db.commit()


def test_delivery_check_endpoint():
    # demo shop: Pune, 3 km radius (seed)
    shop = client.get("/shops/sharma-kirana").json()["shop"]
    lat, lng, radius = shop["lat"], shop["lng"], shop["delivery_radius_km"]
    near = client.post("/shops/sharma-kirana/delivery-check", json={"lat": lat + 0.009, "lng": lng}).json()
    assert near["eligible"] is True and near["radius_km"] == radius and 0.9 < near["distance_km"] < 1.1
    far = client.post("/shops/sharma-kirana/delivery-check", json={"lat": lat + 0.054, "lng": lng}).json()
    assert far["eligible"] is False and far["distance_km"] > radius
    assert client.post("/shops/nope/delivery-check", json={"lat": 1, "lng": 1}).status_code == 404
    assert client.post("/shops/sharma-kirana/delivery-check", json={"lat": 100, "lng": 1}).status_code == 422


def test_delivery_check_shop_without_location():
    import uuid
    from app.models import Shop, Shopkeeper

    email = f"t{uuid.uuid4().hex[:10]}@test.in"
    tok = client.post("/auth/owner/signup", json={"name": "N", "email": email, "password": "secret123"}).json()["access_token"]
    slug = client.put("/owner/shop", json={"name": "No Pin Shop"}, headers={"Authorization": f"Bearer {tok}"}).json()["slug"]
    try:
        r = client.post(f"/shops/{slug}/delivery-check", json={"lat": 18.5, "lng": 73.8})
        assert r.status_code == 422 and r.json()["detail"]["code"] == "SHOP_LOCATION_NOT_SET"
        assert "delivery area" in r.json()["detail"]["message"]
    finally:
        with SessionLocal() as db:
            s = db.scalar(select(Shop).where(Shop.slug == slug))
            o = db.get(Shopkeeper, s.owner_id)
            db.delete(s); db.delete(o); db.commit()

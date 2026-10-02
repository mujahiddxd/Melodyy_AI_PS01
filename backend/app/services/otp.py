"""OTP generation, hashing and delivery.

The code itself is never stored in the database: only sha256(code + phone + OTP_SECRET).
Delivery goes through an OTPProvider (mock | msg91; twilio is a stub). In mock mode the plain code is kept
in this process's memory so the demo SMS inbox can show it; it is lost on restart, which is fine for a demo.
"""
import hashlib
import hmac
import logging
import secrets
from datetime import datetime
from typing import Protocol

import httpx

from app.config import get_settings

log = logging.getLogger("hod.otp")

OTP_TTL_SECONDS = 300
MAX_ATTEMPTS = 5
MAX_REQUESTS = 3
REQUEST_WINDOW_SECONDS = 600
RESEND_AFTER_SECONDS = 30


def generate_code() -> str:
    """Random 6 digits, from the OS CSPRNG. Never a fixed code."""
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_code(code: str, phone: str) -> str:
    return hashlib.sha256((code + phone + get_settings().otp_secret).encode()).hexdigest()


def code_matches(code: str, phone: str, code_hash: str) -> bool:
    return hmac.compare_digest(hash_code(code, phone), code_hash)


class OTPProvider(Protocol):
    name: str

    def send(self, phone: str, code: str, otp_id: int) -> None:
        """Deliver the code. Raise on failure."""


class MockProvider:
    """No SMS. Keeps the latest plain code per phone in memory for the Demo SMS inbox."""

    name = "mock"

    def __init__(self) -> None:
        self._latest: dict[str, tuple[int, str]] = {}  # phone -> (otp_request id, code)

    def send(self, phone: str, code: str, otp_id: int) -> None:
        self._latest[phone] = (otp_id, code)

    def latest(self, phone: str) -> tuple[int, str] | None:
        return self._latest.get(phone)


class Msg91Provider:
    """MSG91 OTP API v5. Needs MSG91_AUTH_KEY and a DLT-approved MSG91_TEMPLATE_ID.

    We pass our own code in `otp`, so verification stays in our hash-based flow.
    """

    name = "msg91"

    def send(self, phone: str, code: str, otp_id: int) -> None:
        s = get_settings()
        if not (s.msg91_auth_key.strip() and s.msg91_template_id.strip()):
            raise RuntimeError("MSG91_AUTH_KEY / MSG91_TEMPLATE_ID are not set")
        r = httpx.post(
            "https://control.msg91.com/api/v5/otp",
            params={
                "template_id": s.msg91_template_id.strip(),
                "mobile": f"91{phone}",
                "otp": code,
                "otp_expiry": OTP_TTL_SECONDS // 60,
            },
            headers={"authkey": s.msg91_auth_key.strip(), "Content-Type": "application/json"},  # key in a header, not the URL
            json={},
            timeout=10.0,
        )
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if r.status_code != 200 or body.get("type") != "success":
            # message only: never log the request (it contains the code)
            raise RuntimeError(f"MSG91 rejected the request: {str(body.get('message', r.status_code))[:200]}")


class TwilioProvider:
    """Stub: not wired. Same interface, for a later stage."""

    name = "twilio"

    def send(self, phone: str, code: str, otp_id: int) -> None:
        raise NotImplementedError("Twilio OTP is not wired yet")


_mock = MockProvider()


def get_provider() -> OTPProvider:
    name = get_settings().otp_provider.lower()
    if name == "msg91":
        return Msg91Provider()
    if name == "twilio":
        return TwilioProvider()
    return _mock


def mock_latest(phone: str) -> tuple[int, str] | None:
    return _mock.latest(phone)


def is_mock_mode() -> bool:
    return get_settings().otp_provider.lower() not in ("msg91", "twilio")


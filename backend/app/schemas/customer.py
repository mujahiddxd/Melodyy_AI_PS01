from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.auth import PHONE_RE, normalize_phone


def _phone(v: str) -> str:
    v = normalize_phone(v)
    if not PHONE_RE.match(v):
        raise ValueError("Enter a valid 10-digit mobile number")
    return v


class OtpRequestIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    phone: str

    @field_validator("phone")
    @classmethod
    def _v(cls, v: str) -> str:
        return _phone(v)


class OtpVerifyIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    phone: str
    code: str = Field(pattern=r"^\d{6}$")

    @field_validator("phone")
    @classmethod
    def _v(cls, v: str) -> str:
        return _phone(v)


class OtpRequestOut(BaseModel):
    status: Literal["sent"] = "sent"
    expires_in_seconds: int
    resend_after_seconds: int
    provider: str


class CustomerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    phone: str
    name: str | None


class CustomerAuthOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    customer: CustomerOut


class DemoMessage(BaseModel):
    phone: str
    code: str
    created_at: datetime
    expires_at: datetime


class DemoInboxOut(BaseModel):
    messages: list[DemoMessage]


class AddressIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    label: Literal["Home", "Work", "Other"]
    address_text: str = Field(min_length=1, max_length=500)
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class AddressOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    address_text: str
    lat: float
    lng: float
    created_at: datetime


class AddressList(BaseModel):
    items: list[AddressOut]


class DeliveryCheckIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class DeliveryCheckOut(BaseModel):
    eligible: bool
    distance_km: float
    radius_km: float

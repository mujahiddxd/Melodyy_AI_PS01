import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PHONE_RE = re.compile(r"^[6-9]\d{9}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")


def normalize_phone(raw: str) -> str:
    digits = re.sub(r"[\s\-]", "", raw)
    if digits.startswith("+91"):
        digits = digits[3:]
    elif len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    return digits


class OwnerSignup(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=120)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = None
    password: str = Field(min_length=6, max_length=72)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str | None) -> str | None:
        if not v:
            return None
        v = v.lower()
        if not EMAIL_RE.match(v):
            raise ValueError("Enter a valid email address")
        return v

    @field_validator("phone")
    @classmethod
    def _phone(cls, v: str | None) -> str | None:
        if not v:
            return None
        v = normalize_phone(v)
        if not PHONE_RE.match(v):
            raise ValueError("Enter a valid 10-digit mobile number")
        return v

    @model_validator(mode="after")
    def _one_contact(self):
        if not self.email and not self.phone:
            raise ValueError("Provide a phone number or an email")
        return self


class OwnerLogin(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    identifier: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=72)


class AuthOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    shop_id: int | None
    has_shop: bool

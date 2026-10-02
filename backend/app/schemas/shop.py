import re
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.common import Money

VPA_RE = re.compile(r"^[\w.\-]{2,}@[\w]{2,}$")


class ShopIn(BaseModel):
    """PUT /owner/shop body. Only the fields that are sent are changed."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=1000)
    address_text: str | None = Field(default=None, max_length=500)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    delivery_radius_km: Decimal | None = Field(default=None, ge=Decimal("0.5"), le=10, decimal_places=2)
    upi_vpa: str | None = None
    min_order_value: Decimal | None = Field(default=None, ge=0, le=Decimal("99999999"), decimal_places=2)
    delivery_fee: Decimal | None = Field(default=None, ge=0, le=Decimal("99999999"), decimal_places=2)
    is_open: bool | None = None

    @field_validator("upi_vpa")
    @classmethod
    def _vpa(cls, v: str | None) -> str | None:
        if not v:
            return None
        if not VPA_RE.match(v):
            raise ValueError("UPI ID must look like name@bank")
        return v

    @model_validator(mode="after")
    def _lat_lng_together(self):
        if (self.lat is None) != (self.lng is None):
            raise ValueError("lat and lng must be set together")
        return self


class ShopPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    description: str | None
    address_text: str | None
    lat: float | None
    lng: float | None
    delivery_radius_km: float | None
    photo_url: str | None
    upi_vpa: str | None
    min_order_value: Money
    delivery_fee: Money
    is_open: bool


class ShopCard(BaseModel):
    """One shop in the public list. A strict subset of what GET /shops/{slug} already shows publicly: no owner, no UPI
    ID, no coordinates."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    description: str | None
    address_text: str | None
    photo_url: str | None
    is_open: bool
    delivery_radius_km: float | None
    min_order_value: Money
    delivery_fee: Money
    product_count: int = 0


class ShopList(BaseModel):
    items: list[ShopCard]
    total: int
    page: int
    page_size: int
    has_more: bool


class ShopOwner(ShopPublic):
    photo_public_id: str | None
    is_configured: bool


class PhotoOut(BaseModel):
    photo_url: str
    photo_public_id: str


class GeoResult(BaseModel):
    display_name: str
    lat: float
    lng: float

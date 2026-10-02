from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.common import Money, Qty
from app.schemas.shop import ShopPublic

SellMode = Literal["pack", "loose"]
PackUnit = Literal["g", "kg", "ml", "l", "pc", "dozen", "packet"]
StockStatus = Literal["in_stock", "low_stock", "out_of_stock"]

_MONEY_MAX = Decimal("99999999")
_QTY_MAX = Decimal("9999999")


def _clean_aliases(v: list[str]) -> list[str]:
    seen: list[str] = []
    for a in v:
        a = a.strip()
        if not a or a.lower() in (s.lower() for s in seen):
            continue
        if len(a) > 60:
            raise ValueError("Each alias must be 60 characters or fewer")
        seen.append(a)
    if len(seen) > 30:
        raise ValueError("At most 30 aliases")
    return seen


class ProductIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=160)
    brand: str | None = Field(default=None, max_length=80)
    category: str = Field(min_length=1, max_length=60)
    sell_mode: SellMode = "pack"
    pack_size: Decimal = Field(gt=0, le=_QTY_MAX, decimal_places=3)
    pack_unit: PackUnit
    price: Decimal = Field(gt=0, le=_MONEY_MAX, decimal_places=2)
    stock_qty: Decimal = Field(ge=0, le=_QTY_MAX, decimal_places=3)
    low_stock_threshold: Decimal = Field(default=Decimal("5"), ge=0, le=_QTY_MAX, decimal_places=3)
    max_normal_qty: Decimal | None = Field(default=None, gt=0, le=_QTY_MAX, decimal_places=3)
    aliases: list[str] = Field(default_factory=list)
    shelf: str | None = Field(default=None, max_length=40)

    @field_validator("aliases")
    @classmethod
    def _aliases(cls, v):
        return _clean_aliases(v)

    @field_validator("brand", "shelf")
    @classmethod
    def _blank_to_none(cls, v):
        return v or None


class ProductPatch(BaseModel):
    """Partial update: any field of ProductIn, plus is_active. Explicit null only where the column is nullable."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=160)
    brand: str | None = Field(default=None, max_length=80)
    category: str | None = Field(default=None, min_length=1, max_length=60)
    sell_mode: SellMode | None = None
    pack_size: Decimal | None = Field(default=None, gt=0, le=_QTY_MAX, decimal_places=3)
    pack_unit: PackUnit | None = None
    price: Decimal | None = Field(default=None, gt=0, le=_MONEY_MAX, decimal_places=2)
    stock_qty: Decimal | None = Field(default=None, ge=0, le=_QTY_MAX, decimal_places=3)
    low_stock_threshold: Decimal | None = Field(default=None, ge=0, le=_QTY_MAX, decimal_places=3)
    max_normal_qty: Decimal | None = Field(default=None, gt=0, le=_QTY_MAX, decimal_places=3)
    aliases: list[str] | None = None
    shelf: str | None = Field(default=None, max_length=40)
    is_active: bool | None = None

    @field_validator("aliases")
    @classmethod
    def _aliases(cls, v):
        return None if v is None else _clean_aliases(v)

    @model_validator(mode="after")
    def _no_null_for_required(self):
        nullable = {"brand", "max_normal_qty", "shelf"}
        for f in self.model_fields_set - nullable:
            if getattr(self, f) is None:
                raise ValueError(f"{f} cannot be null")
        return self


class ProductPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    brand: str | None
    category: str
    sell_mode: SellMode
    pack_size: Qty
    pack_unit: PackUnit
    price: Money
    stock_qty: Qty
    stock_status: StockStatus
    aliases: list[str]
    shelf: str | None


class ProductOwner(ProductPublic):
    low_stock_threshold: Qty
    max_normal_qty: Qty | None
    is_active: bool
    updated_at: datetime


class ProductList(BaseModel):
    items: list[ProductOwner]
    total: int


class CategoryGroup(BaseModel):
    name: str
    products: list[ProductPublic]


class PublicShopOut(BaseModel):
    shop: ShopPublic
    categories: list[CategoryGroup]

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, Text, func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

SELL_MODES = ("pack", "loose")
PACK_UNITS = ("g", "kg", "ml", "l", "pc", "dozen", "packet")
UPLOAD_KINDS = ("shop_photo", "list_image", "audio")


class Shopkeeper(Base):
    __tablename__ = "shopkeepers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(15), unique=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Shop(Base):
    __tablename__ = "shops"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("shopkeepers.id"))
    name: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(180), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    address_text: Mapped[str | None] = mapped_column(Text)
    lat: Mapped[float | None] = mapped_column()
    lng: Mapped[float | None] = mapped_column()
    delivery_radius_km: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    photo_url: Mapped[str | None] = mapped_column(Text)
    photo_public_id: Mapped[str | None] = mapped_column(Text)
    upi_vpa: Mapped[str | None] = mapped_column(String(120))
    min_order_value: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, server_default="0")
    delivery_fee: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, server_default="0")
    is_open: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    products: Mapped[list["Product"]] = relationship(back_populates="shop")


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (Index("ix_products_shop_active", "shop_id", "is_active"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"))
    name: Mapped[str] = mapped_column(String(160))
    brand: Mapped[str | None] = mapped_column(String(80))
    category: Mapped[str] = mapped_column(String(60))
    sell_mode: Mapped[str] = mapped_column(Enum(*SELL_MODES, name="sell_mode"))
    pack_size: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    pack_unit: Mapped[str] = mapped_column(Enum(*PACK_UNITS, name="pack_unit"))
    # price: per pack, or per base unit if loose
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    # stock_qty: packs, or base units if loose
    stock_qty: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    low_stock_threshold: Mapped[Decimal] = mapped_column(Numeric(10, 3), default=5, server_default="5")
    max_normal_qty: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    aliases: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default="{}")
    shelf: Mapped[str | None] = mapped_column(String(40))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    shop: Mapped[Shop] = relationship(back_populates="products")

    @property
    def stock_status(self) -> str:
        if self.stock_qty <= 0:
            return "out_of_stock"
        if self.stock_qty <= self.low_stock_threshold:
            return "low_stock"
        return "in_stock"


class PriceHistory(Base):
    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    old_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    new_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Upload(Base):
    __tablename__ = "uploads"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int | None] = mapped_column(ForeignKey("shops.id"))
    # customer_id gets its FK in Stage 2, when the customers table exists
    customer_id: Mapped[int | None] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(Enum(*UPLOAD_KINDS, name="upload_kind"))
    url: Mapped[str] = mapped_column(Text)
    public_id: Mapped[str | None] = mapped_column(Text)
    mime: Mapped[str | None] = mapped_column(String(80))
    bytes: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

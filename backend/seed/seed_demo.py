"""Seed the demo shop. Safe to re-run: it deletes and recreates the demo data.

Usage (from /backend):  python seed/seed_demo.py
"""
import argparse
import csv
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from passlib.context import CryptContext  # noqa: E402
from sqlalchemy import delete, select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import PriceHistory, Product, Shop, Shopkeeper, Upload  # noqa: E402

DEMO_EMAIL = "demo@shop.in"
DEMO_PASSWORD = "demo1234"
DEMO_SLUG = "sharma-kirana"
CSV_PATH = Path(__file__).resolve().parent / "products.csv"

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def reset_demo(db) -> None:
    owner = db.scalar(select(Shopkeeper).where(Shopkeeper.email == DEMO_EMAIL))
    shop = db.scalar(select(Shop).where(Shop.slug == DEMO_SLUG))
    if shop:
        pids = select(Product.id).where(Product.shop_id == shop.id)
        db.execute(delete(PriceHistory).where(PriceHistory.product_id.in_(pids)))
        db.execute(delete(Upload).where(Upload.shop_id == shop.id))
        db.execute(delete(Product).where(Product.shop_id == shop.id))
        db.delete(shop)
        db.flush()
    if owner:
        db.delete(owner)
        db.flush()


def load_products(shop_id: int) -> list[Product]:
    products = []
    with CSV_PATH.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            max_qty = row["max_normal_qty"].strip()
            products.append(
                Product(
                    shop_id=shop_id,
                    name=row["name"],
                    brand=row["brand"] or None,
                    category=row["category"],
                    sell_mode=row["sell_mode"],
                    pack_size=Decimal(row["pack_size"]),
                    pack_unit=row["pack_unit"],
                    price=Decimal(row["price"]),
                    stock_qty=Decimal(row["stock_qty"]),
                    low_stock_threshold=Decimal(row["low_stock_threshold"]),
                    max_normal_qty=Decimal(max_qty) if max_qty else None,
                    aliases=[a.strip() for a in row["aliases"].split("|") if a.strip()],
                    shelf=row["shelf"] or None,
                    is_active=True,
                )
            )
    return products


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-history", action="store_true", help="(Stage 7) past orders for charts")
    args = parser.parse_args()

    with SessionLocal() as db:
        reset_demo(db)

        owner = Shopkeeper(
            name="Ramesh Sharma",
            email=DEMO_EMAIL,
            password_hash=pwd.hash(DEMO_PASSWORD),
        )
        db.add(owner)
        db.flush()

        shop = Shop(
            owner_id=owner.id,
            name="Sharma Kirana",
            slug=DEMO_SLUG,
            description="Your neighbourhood kirana store. Atta, dal, oil, dairy and daily needs.",
            address_text="Shop 4, Karve Road, Kothrud, Pune, Maharashtra 411038",
            lat=18.5074,
            lng=73.8077,
            delivery_radius_km=Decimal("3.00"),
            photo_url="/placeholder-shop.svg",  # served by the frontend; replaced by Cloudinary upload in Stage 1
            upi_vpa="sharmakirana@upi",
            min_order_value=Decimal("0"),
            delivery_fee=Decimal("0"),
        )
        db.add(shop)
        db.flush()

        products = load_products(shop.id)
        db.add_all(products)
        db.commit()

        out_of_stock = [p.name for p in products if p.stock_qty == 0]
        low_stock = [p.name for p in products if 0 < p.stock_qty <= p.low_stock_threshold]
        print(f"Seeded shop '{shop.name}' (slug={shop.slug}) with {len(products)} products.")
        print(f"Owner login: {DEMO_EMAIL} / {DEMO_PASSWORD}")
        print(f"Out of stock: {out_of_stock}")
        print(f"Low stock:    {low_stock}")
        if args.with_history:
            print("Note: --with-history is added in Stage 7 (no orders table yet); ignored.")


if __name__ == "__main__":
    main()

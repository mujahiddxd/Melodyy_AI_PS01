"""The demo catalog (seed/products.csv) as in-memory Product objects, so matcher tests need no database."""
import csv
from decimal import Decimal
from pathlib import Path

from app.models import Product

CSV_PATH = Path(__file__).resolve().parent.parent / "seed" / "products.csv"


def load_products(shop_id: int = 1) -> list[Product]:
    products = []
    with CSV_PATH.open(encoding="utf-8", newline="") as f:
        for i, row in enumerate(csv.DictReader(f), start=1):
            mx = row["max_normal_qty"].strip()
            products.append(Product(
                id=i, shop_id=shop_id, name=row["name"], brand=row["brand"] or None, category=row["category"],
                sell_mode=row["sell_mode"], pack_size=Decimal(row["pack_size"]), pack_unit=row["pack_unit"],
                price=Decimal(row["price"]), stock_qty=Decimal(row["stock_qty"]),
                low_stock_threshold=Decimal(row["low_stock_threshold"]),
                max_normal_qty=Decimal(mx) if mx else None,
                aliases=[a.strip() for a in row["aliases"].split("|") if a.strip()],
                shelf=row["shelf"] or None, is_active=True,
            ))
    return products

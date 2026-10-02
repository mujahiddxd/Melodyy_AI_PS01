from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import api_error
from app.models import Product, Shop
from app.schemas.product import CategoryGroup, ProductPublic, PublicShopOut
from app.schemas.shop import GeoResult, ShopPublic
from app.services import geo

router = APIRouter(tags=["public"])


@router.get("/shops/{slug}", response_model=PublicShopOut)
def public_shop(slug: str, db: Session = Depends(get_db)):
    shop = db.scalar(select(Shop).where(Shop.slug == slug))
    if shop is None:
        raise api_error(404, "NOT_FOUND", "Shop not found.")
    products = db.scalars(
        select(Product)
        .where(Product.shop_id == shop.id, Product.is_active.is_(True))
        .order_by(Product.category, Product.name, Product.id)
    ).all()
    groups: dict[str, list[ProductPublic]] = {}
    for p in products:
        groups.setdefault(p.category, []).append(ProductPublic.model_validate(p))
    return PublicShopOut(
        shop=ShopPublic.model_validate(shop),  # no owner fields exist on this schema
        categories=[CategoryGroup(name=n, products=ps) for n, ps in groups.items()],
    )


@router.get("/geo/search", response_model=list[GeoResult])
def geo_search(q: str = Query(default="", max_length=200)):
    return geo.search(q)

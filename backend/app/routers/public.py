from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import api_error
from app.models import Product, Shop
from app.schemas.customer import DeliveryCheckIn, DeliveryCheckOut
from app.schemas.product import CategoryGroup, ProductPublic, PublicShopOut
from app.schemas.shop import GeoResult, ShopCard, ShopList, ShopPublic
from app.services import geo

router = APIRouter(tags=["public"])


LIKE_ESCAPE = "!"


def _like(term: str) -> str:
    """A contains-pattern for `term` in which %, _ and the escape character are plain characters, so a search for
    "100%" or "a_b" does not match everything."""
    for ch in (LIKE_ESCAPE, "%", "_"):
        term = term.replace(ch, LIKE_ESCAPE + ch)
    return f"%{term}%"


@router.get("/shops", response_model=ShopList)
def list_shops(
    q: str = Query(default="", max_length=100),
    page: int = Query(default=1, ge=1, le=10000),
    page_size: int = Query(default=12, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Shops a customer can browse: those that finished setup (name, map location and delivery radius), the same rule
    the shop page uses to enable ordering. A shop appears here as soon as its owner saves its location. `q` matches
    the shop name or address, case-insensitively. Open shops come first."""
    configured = (
        Shop.name != "", Shop.lat.is_not(None), Shop.lng.is_not(None), Shop.delivery_radius_km.is_not(None),
    )
    where = list(configured)
    # every word must appear in the name or the address ("sharma kothrud" finds Sharma Kirana, Karve Road, Kothrud)
    for word in q.split()[:6]:
        pattern = _like(word)
        where.append(or_(Shop.name.ilike(pattern, escape=LIKE_ESCAPE),
                         Shop.address_text.ilike(pattern, escape=LIKE_ESCAPE)))

    total = db.scalar(select(func.count()).select_from(Shop).where(*where)) or 0
    count = (
        select(func.count(Product.id)).where(Product.shop_id == Shop.id, Product.is_active.is_(True))
        .correlate(Shop).scalar_subquery()
    )
    rows = db.execute(
        select(Shop, count.label("product_count")).where(*where)
        .order_by(Shop.is_open.desc(), func.lower(Shop.name), Shop.id)
        .limit(page_size).offset((page - 1) * page_size)
    ).all()
    items = [ShopCard.model_validate({**{f: getattr(s, f) for f in ShopCard.model_fields if f != "product_count"},
                                      "product_count": n}) for s, n in rows]
    return ShopList(items=items, total=total, page=page, page_size=page_size, has_more=page * page_size < total)


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


@router.post("/shops/{slug}/delivery-check", response_model=DeliveryCheckOut)
def delivery_check(slug: str, body: DeliveryCheckIn, db: Session = Depends(get_db)):
    shop = db.scalar(select(Shop).where(Shop.slug == slug))
    if shop is None:
        raise api_error(404, "NOT_FOUND", "Shop not found.")
    try:
        result = geo.check_delivery(shop, body.lat, body.lng)
    except geo.ShopLocationNotSet:
        raise api_error(422, "SHOP_LOCATION_NOT_SET", f"{shop.name} hasn't set its delivery area yet.")
    return DeliveryCheckOut(
        eligible=result.eligible, distance_km=round(result.distance_km, 2), radius_km=result.radius_km
    )

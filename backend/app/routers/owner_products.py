from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_owner_shop
from app.errors import api_error
from app.models import PriceHistory, Product, Shop
from app.schemas.product import ProductIn, ProductList, ProductOwner, ProductPatch

router = APIRouter(prefix="/owner/products", tags=["owner products"])


def _own_product(db: Session, shop: Shop, product_id: int) -> Product:
    p = db.get(Product, product_id)
    if p is None:
        raise api_error(404, "NOT_FOUND", "Product not found.")
    if p.shop_id != shop.id:
        raise api_error(403, "FORBIDDEN", "This product belongs to another shop.")
    return p


@router.get("", response_model=ProductList)
def list_products(
    q: str = Query(default="", max_length=100),
    include_inactive: bool = False,
    shop: Shop = Depends(get_owner_shop),
    db: Session = Depends(get_db),
):
    stmt = select(Product).where(Product.shop_id == shop.id)
    if not include_inactive:
        stmt = stmt.where(Product.is_active.is_(True))
    q = q.strip()
    if q:
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        stmt = stmt.where(
            or_(
                Product.name.ilike(like),
                Product.brand.ilike(like),
                Product.category.ilike(like),
                func.array_to_string(Product.aliases, " ").ilike(like),
            )
        )
    items = db.scalars(stmt.order_by(Product.category, Product.name, Product.id)).all()
    return ProductList(items=[ProductOwner.model_validate(p) for p in items], total=len(items))


@router.post("", response_model=ProductOwner, status_code=201)
def create_product(body: ProductIn, shop: Shop = Depends(get_owner_shop), db: Session = Depends(get_db)):
    p = Product(shop_id=shop.id, is_active=True, **body.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@router.patch("/{product_id}", response_model=ProductOwner)
def update_product(
    product_id: int,
    body: ProductPatch,
    shop: Shop = Depends(get_owner_shop),
    db: Session = Depends(get_db),
):
    p = _own_product(db, shop, product_id)
    changes = {f: getattr(body, f) for f in body.model_fields_set}
    old_price = p.price
    for f, v in changes.items():
        setattr(p, f, v)
    if "price" in changes and changes["price"] != old_price:
        db.add(PriceHistory(product_id=p.id, old_price=old_price, new_price=changes["price"]))
    db.commit()
    db.refresh(p)
    return p


@router.delete("/{product_id}", status_code=204)
def delete_product(product_id: int, shop: Shop = Depends(get_owner_shop), db: Session = Depends(get_db)):
    p = _own_product(db, shop, product_id)
    p.is_active = False  # soft delete: order history keeps pointing at the row
    db.commit()
    return Response(status_code=204)

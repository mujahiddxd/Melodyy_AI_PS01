from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_customer
from app.models import Customer, CustomerAddress, Order, OrderItem, Product, Shop
from app.models.conversation import OPEN_ORDER_STATUSES
from app.schemas.customer import AddressIn, AddressList, AddressOut, CustomerOrderItemOut, CustomerOrderList, CustomerOrderRow, CustomerOut

router = APIRouter(prefix="/customer", tags=["customer"])


@router.get("/me", response_model=CustomerOut)
def me(customer: Customer = Depends(get_current_customer)):
    return customer


@router.get("/addresses", response_model=AddressList)
def list_addresses(customer: Customer = Depends(get_current_customer), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(CustomerAddress)
        .where(CustomerAddress.customer_id == customer.id)
        .order_by(CustomerAddress.created_at.desc(), CustomerAddress.id.desc())
    ).all()
    return AddressList(items=[AddressOut.model_validate(r) for r in rows])


@router.post("/addresses", response_model=AddressOut, status_code=201)
def create_address(body: AddressIn, customer: Customer = Depends(get_current_customer), db: Session = Depends(get_db)):
    row = CustomerAddress(customer_id=customer.id, **body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _fmt_qty(value, unit) -> str | None:
    if value is None:
        return None
    text = format(value.normalize(), "f") if hasattr(value, "normalize") else str(value)
    return f"{text} {unit}".strip() if unit else text


@router.get("/orders", response_model=CustomerOrderList)
def my_orders(customer: Customer = Depends(get_current_customer), db: Session = Depends(get_db)):
    """The customer's carts (orders still being built) and past orders, newest first. Prices come from the DB."""
    rows = db.execute(
        select(Order, Shop).join(Shop, Shop.id == Order.shop_id)
        .where(Order.customer_id == customer.id).order_by(Order.id.desc()).limit(100)
    ).all()
    ids = [o.id for o, _ in rows]
    items_by_order: dict[int, list[tuple[OrderItem, str | None]]] = {i: [] for i in ids}
    if ids:
        for item, pname in db.execute(
            select(OrderItem, Product.name).outerjoin(Product, Product.id == OrderItem.product_id)
            .where(OrderItem.order_id.in_(ids), OrderItem.status != "removed").order_by(OrderItem.id)
        ):
            items_by_order[item.order_id].append((item, pname))
    out = CustomerOrderList(cart=[], past=[])
    for order, shop in rows:
        items = items_by_order[order.id]
        is_cart = order.status in OPEN_ORDER_STATUSES
        if is_cart and not items:
            continue  # an empty draft is not a cart
        row = CustomerOrderRow(
            id=order.id, order_no=1000 + order.id, shop_slug=shop.slug, shop_name=shop.name, status=order.status,
            is_cart=is_cart, item_count=len(items), total=f"{order.total:.2f}", created_at=order.created_at,
            confirmed_at=order.confirmed_at,
            items=[
                CustomerOrderItemOut(
                    name=pname or i.name_guess, quantity=_fmt_qty(i.quantity_value, i.unit),
                    line_total=f"{i.line_total:.2f}" if i.line_total is not None else None,
                )
                for i, pname in items
            ],
        )
        (out.cart if is_cart else out.past).append(row)
    return out

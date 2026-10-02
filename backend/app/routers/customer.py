from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_customer
from app.models import Customer, CustomerAddress
from app.schemas.customer import AddressIn, AddressList, AddressOut, CustomerOut

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

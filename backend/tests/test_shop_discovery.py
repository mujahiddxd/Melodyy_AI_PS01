"""Customer shop discovery: GET /shops (list + search + pagination). Uses the dev Postgres; cleans up after itself.

Shops are created the way a shopkeeper does it (signup, then PUT /owner/shop), so these tests also prove that a newly
set-up shop appears without anyone adding it by hand.
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.db import SessionLocal
from app.main import app
from app.models import PriceHistory, Product, Shop, Shopkeeper, Upload

client = TestClient(app)

PRODUCT = {"name": "Atta 1kg", "category": "Atta", "sell_mode": "pack", "pack_size": "1", "pack_unit": "kg",
           "price": "50.00", "stock_qty": "10"}


@pytest.fixture
def token():
    return uuid.uuid4().hex[:8]


@pytest.fixture
def make_shop():
    """make_shop(name, address=..., configured=True, is_open=True) -> {slug, headers}. Removed afterwards."""
    owners: list[str] = []

    def make(name, address="Kothrud, Pune", configured=True, is_open=True, **extra):
        email = f"d{uuid.uuid4().hex[:10]}@test.in"
        owners.append(email)
        r = client.post("/auth/owner/signup", json={"name": "Disc Owner", "email": email, "password": "secret123"})
        assert r.status_code == 201, r.text
        headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
        body = {"name": name, "address_text": address, "is_open": is_open, "upi_vpa": "secret@upi", **extra}
        if configured:
            body |= {"lat": 18.5074, "lng": 73.8077, "delivery_radius_km": 3}
        r = client.put("/owner/shop", json=body, headers=headers)
        assert r.status_code == 200, r.text
        return {"slug": r.json()["slug"], "headers": headers, "body": body}

    yield make
    with SessionLocal() as db:
        for email in owners:
            o = db.scalar(select(Shopkeeper).where(Shopkeeper.email == email))
            if o is None:
                continue
            for shop in db.scalars(select(Shop).where(Shop.owner_id == o.id)):
                pids = select(Product.id).where(Product.shop_id == shop.id)
                db.execute(delete(PriceHistory).where(PriceHistory.product_id.in_(pids)))
                db.execute(delete(Product).where(Product.shop_id == shop.id))
                db.execute(delete(Upload).where(Upload.shop_id == shop.id))
                db.delete(shop)
            db.delete(o)
        db.commit()


def listing(**params):
    r = client.get("/shops", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def names(data):
    return [s["name"] for s in data["items"]]


# ---- visibility and auto-appearing ---------------------------------------------------------------------
def test_new_shop_appears_automatically_once_setup_is_finished(make_shop, token):
    shop = make_shop(f"Setup Store {token}", configured=False)  # name only: delivery area not set yet
    assert listing(q=token)["total"] == 0  # the shop page would say "Ordering unavailable", so it is not listed

    r = client.put("/owner/shop", json={"name": f"Setup Store {token}", "lat": 18.5, "lng": 73.8, "delivery_radius_km": 2},
                   headers=shop["headers"])
    assert r.status_code == 200
    data = listing(q=token)  # no manual step in between
    assert data["total"] == 1 and data["items"][0]["slug"] == shop["slug"]


def test_card_has_only_public_fields(make_shop, token):
    make_shop(f"Fields {token}", description="Fresh daily", min_order_value="99", delivery_fee="15")
    card = listing(q=token)["items"][0]
    assert set(card) == {"id", "name", "slug", "description", "address_text", "photo_url", "is_open",
                         "delivery_radius_km", "min_order_value", "delivery_fee", "product_count"}
    assert card["delivery_radius_km"] == 3.0 and card["min_order_value"] == "99.00" and card["delivery_fee"] == "15.00"
    assert card["photo_url"] is None  # the UI shows a fallback image
    flat = str(card).lower()
    for private in ("secret@upi", "owner", "email", "phone", "password", "lat", "lng", "token", "hash"):
        assert private not in flat, private


def test_response_never_contains_shopkeeper_details(make_shop, token):
    make_shop(f"Private {token}")
    raw = client.get("/shops", params={"q": token}).text.lower()
    assert "disc owner" not in raw and "@test.in" not in raw and "secret@upi" not in raw


def test_closed_shops_are_listed_after_open_ones(make_shop, token):
    make_shop(f"A Closed {token}", is_open=False)
    make_shop(f"Z Open {token}")
    data = listing(q=token)
    assert names(data) == [f"Z Open {token}", f"A Closed {token}"]
    assert [s["is_open"] for s in data["items"]] == [True, False]


def test_product_count_counts_only_active_products(make_shop, token):
    shop = make_shop(f"Counts {token}")
    assert listing(q=token)["items"][0]["product_count"] == 0
    pid = client.post("/owner/products", json=PRODUCT, headers=shop["headers"]).json()["id"]
    assert listing(q=token)["items"][0]["product_count"] == 1
    assert client.delete(f"/owner/products/{pid}", headers=shop["headers"]).status_code == 204
    assert listing(q=token)["items"][0]["product_count"] == 0


# ---- search ---------------------------------------------------------------------------------------------
def test_search_by_name_is_case_insensitive_and_partial(make_shop, token):
    make_shop(f"Sharma Kirana {token}")
    make_shop(f"Gupta Mart {token}")
    assert names(listing(q=f"sharma kirana {token}")) == [f"Sharma Kirana {token}"]
    assert names(listing(q=f"SHARMA")) and all("sharma" in n.lower() for n in names(listing(q="SHARMA")))
    assert listing(q=token)["total"] == 2


def test_search_by_location(make_shop, token):
    make_shop(f"Loc A {token}", address=f"Karve Road, Kothrud, Pune {token}")
    make_shop(f"Loc B {token}", address=f"Andheri West, Mumbai {token}")
    assert names(listing(q=f"kothrud {token}")) == [f"Loc A {token}"]
    assert names(listing(q=f"MUMBAI {token}")) == [f"Loc B {token}"]


def test_search_with_no_match_is_an_empty_list_not_an_error(make_shop, token):
    data = listing(q=f"no-such-shop-{token}")
    assert data == {"items": [], "total": 0, "page": 1, "page_size": 12, "has_more": False}


def test_blank_search_lists_everything(make_shop, token):
    make_shop(f"Blank {token}")
    assert listing(q="   ")["total"] == listing()["total"] >= 1


def test_wildcards_in_the_search_are_plain_characters(make_shop, token):
    make_shop(f"Fifty%Off {token}")
    make_shop(f"Under_Score {token}")
    make_shop(f"Plain Shop {token}")
    pct = listing(q="%", page_size=50)
    assert pct["items"] and all("%" in (s["name"] + (s["address_text"] or "")) for s in pct["items"])
    assert f"Fifty%Off {token}" in names(pct) and f"Plain Shop {token}" not in names(pct)
    us = listing(q="_", page_size=50)
    assert us["items"] and all("_" in (s["name"] + (s["address_text"] or "")) for s in us["items"])
    assert names(listing(q=f"Under_Score {token}")) == [f"Under_Score {token}"]
    assert listing(q=f"Under_Scor_ {token}")["total"] == 0  # "_" is not "any character"


def test_sql_injection_attempt_is_just_text(make_shop, token):
    make_shop(f"Safe {token}")
    assert listing(q="'; DROP TABLE shops; --")["total"] == 0
    assert listing(q=token)["total"] == 1


# ---- pagination -----------------------------------------------------------------------------------------
def test_pagination(make_shop, token):
    for n in "ABC":
        make_shop(f"Page {n} {token}")
    p1 = listing(q=token, page=1, page_size=2)
    p2 = listing(q=token, page=2, page_size=2)
    assert names(p1) == [f"Page A {token}", f"Page B {token}"] and p1["has_more"] is True and p1["total"] == 3
    assert names(p2) == [f"Page C {token}"] and p2["has_more"] is False
    assert listing(q=token, page=3, page_size=2)["items"] == []  # past the end: empty, not an error


@pytest.mark.parametrize("params", [{"page": 0}, {"page_size": 0}, {"page_size": 51}, {"q": "x" * 101}, {"page": "abc"}])
def test_invalid_parameters_are_rejected(params):
    assert client.get("/shops", params=params).status_code == 422


# ---- the existing public shop page is untouched ---------------------------------------------------------
def test_existing_shop_page_still_works_and_cards_link_to_it(make_shop, token):
    shop = make_shop(f"Linked {token}")
    client.post("/owner/products", json=PRODUCT, headers=shop["headers"])
    slug = listing(q=token)["items"][0]["slug"]
    page = client.get(f"/shops/{slug}")
    assert page.status_code == 200
    assert page.json()["shop"]["slug"] == slug and page.json()["categories"][0]["products"][0]["name"] == "Atta 1kg"
    assert client.get("/shops/definitely-not-a-shop").status_code == 404


def test_unconfigured_shop_page_still_loads_directly(make_shop, token):
    shop = make_shop(f"Direct {token}", configured=False)
    assert client.get(f"/shops/{shop['slug']}").status_code == 200  # old links keep working, it is just not listed


def test_every_search_word_must_match_the_name_or_the_address(make_shop, token):
    make_shop(f"Sharma Kirana {token}", address=f"Karve Road, Kothrud, Pune")
    make_shop(f"Sharma Stores {token}", address=f"Andheri, Mumbai")
    assert names(listing(q=f"sharma kothrud {token}")) == [f"Sharma Kirana {token}"]  # word 1 in name, word 2 in address
    assert listing(q=f"kothrud pune {token}")["total"] == 1  # words may be separated by commas in the address
    assert listing(q=f"sharma nowhere {token}")["total"] == 0  # all words are required
    assert sorted(names(listing(q=f"sharma {token}"))) == sorted([f"Sharma Kirana {token}", f"Sharma Stores {token}"])

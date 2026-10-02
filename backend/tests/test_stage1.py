"""Stage 1 API tests. Run against the dev Postgres (docker compose up -d); they clean up after themselves.

    cd backend; .venv\\Scripts\\python -m pytest tests -q
"""
import io
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models import PriceHistory, Product, Shop, Shopkeeper, Upload
from app.services import geo, storage

client = TestClient(app)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


@pytest.fixture(autouse=True)
def local_storage(monkeypatch):
    monkeypatch.setattr(get_settings(), "cloudinary_url", "")


@pytest.fixture
def owner():
    """A fresh shopkeeper; removed with all its data afterwards."""
    email = f"t{uuid.uuid4().hex[:10]}@test.in"
    r = client.post("/auth/owner/signup", json={"name": "Test Owner", "email": email, "password": "secret123"})
    assert r.status_code == 201, r.text
    yield {"email": email, "headers": {"Authorization": f"Bearer {r.json()['access_token']}"}}
    with SessionLocal() as db:
        o = db.scalar(select(Shopkeeper).where(Shopkeeper.email == email))
        for shop in db.scalars(select(Shop).where(Shop.owner_id == o.id)):
            pids = select(Product.id).where(Product.shop_id == shop.id)
            db.execute(delete(PriceHistory).where(PriceHistory.product_id.in_(pids)))
            db.execute(delete(Product).where(Product.shop_id == shop.id))
            db.execute(delete(Upload).where(Upload.shop_id == shop.id))
            storage.delete(shop.photo_public_id)
            db.delete(shop)
        db.delete(o)
        db.commit()


SHOP = {
    "name": "Test Kirana", "address_text": "Karve Road, Pune", "lat": 18.5074, "lng": 73.8077,
    "delivery_radius_km": 3, "upi_vpa": "testshop@upi",
}
PRODUCT = {
    "name": "Amul Butter 100g", "brand": "Amul", "category": "Dairy", "sell_mode": "pack",
    "pack_size": "100", "pack_unit": "g", "price": "54.00", "stock_qty": "10", "aliases": ["butter", "makkhan"],
}


def test_signup_login_and_errors(owner):
    r = client.post("/auth/owner/login", json={"identifier": owner["email"], "password": "secret123"})
    assert r.status_code == 200 and r.json()["has_shop"] is False and r.json()["shop_id"] is None
    r = client.post("/auth/owner/login", json={"identifier": owner["email"], "password": "wrong"})
    assert r.status_code == 401 and r.json()["detail"] == "Incorrect email/phone or password."
    r = client.post("/auth/owner/login", json={"identifier": "nobody@test.in", "password": "x12345"})
    assert r.status_code == 401
    r = client.post("/auth/owner/signup", json={"name": "Dup", "email": owner["email"], "password": "secret123"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "CONFLICT"


def test_signup_validation():
    assert client.post("/auth/owner/signup", json={"name": "A", "password": "secret123"}).status_code == 422
    assert client.post("/auth/owner/signup", json={"name": "A", "phone": "12345", "password": "secret123"}).status_code == 422
    assert client.post("/auth/owner/signup", json={"name": "A", "email": "a@b.in", "password": "123"}).status_code == 422


def test_auth_required_and_wrong_role():
    for method, path in [("get", "/owner/shop"), ("put", "/owner/shop"), ("get", "/owner/products"), ("post", "/owner/shop/photo")]:
        assert getattr(client, method)(path).status_code == 401, path
    assert client.get("/owner/shop", headers={"Authorization": "Bearer garbage"}).status_code == 401
    from app.security import create_access_token

    tok = create_access_token(1, "customer")
    assert client.get("/owner/shop", headers={"Authorization": f"Bearer {tok}"}).status_code == 403


def test_shop_setup_and_unique_slug(owner):
    h = owner["headers"]
    assert client.get("/owner/shop", headers=h).status_code == 404
    r = client.put("/owner/shop", json=SHOP, headers=h)
    assert r.status_code == 200, r.text
    shop = r.json()
    assert shop["slug"].startswith("test-kirana") and shop["is_configured"] is True
    assert shop["min_order_value"] == "0.00" and shop["delivery_radius_km"] == 3.0
    # update keeps the slug
    r = client.put("/owner/shop", json={**SHOP, "name": "Renamed", "delivery_radius_km": 2}, headers=h)
    assert r.json()["slug"] == shop["slug"] and r.json()["delivery_radius_km"] == 2.0
    # login now reports the shop
    r = client.post("/auth/owner/login", json={"identifier": owner["email"], "password": "secret123"})
    assert r.json()["has_shop"] is True and r.json()["shop_id"] == shop["id"]


def test_slug_collision(owner):
    other = client.post("/auth/owner/signup", json={"name": "O2", "email": f"t{uuid.uuid4().hex[:10]}@test.in", "password": "secret123"})
    h2 = {"Authorization": f"Bearer {other.json()['access_token']}"}
    a = client.put("/owner/shop", json=SHOP, headers=owner["headers"]).json()
    b = client.put("/owner/shop", json=SHOP, headers=h2).json()
    assert a["slug"] != b["slug"] and b["slug"].startswith("test-kirana-")
    with SessionLocal() as db:
        s = db.get(Shop, b["id"])
        o = db.get(Shopkeeper, s.owner_id)
        db.delete(s); db.delete(o); db.commit()


@pytest.mark.parametrize("patch", [
    {"upi_vpa": "not-a-vpa"}, {"delivery_radius_km": 0.2}, {"delivery_radius_km": 11},
    {"lat": 120, "lng": 10}, {"lat": 10.0, "lng": None}, {"min_order_value": -1},
])
def test_shop_validation(owner, patch):
    assert client.put("/owner/shop", json={**SHOP, **patch}, headers=owner["headers"]).status_code == 422


def test_photo_upload_replace_and_validation(owner):
    h = owner["headers"]
    assert client.post("/owner/shop/photo", headers=h, files={"file": ("a.png", PNG, "image/png")}).status_code == 404
    client.put("/owner/shop", json=SHOP, headers=h)

    r = client.post("/owner/shop/photo", headers=h, files={"file": ("a.txt", b"hello", "text/plain")})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "FILE_TYPE_NOT_ALLOWED"
    # claims to be a PNG but isn't
    r = client.post("/owner/shop/photo", headers=h, files={"file": ("a.png", b"not an image", "image/png")})
    assert r.status_code == 400
    big = PNG + b"\x00" * (5 * 1024 * 1024)
    r = client.post("/owner/shop/photo", headers=h, files={"file": ("a.png", big, "image/png")})
    assert r.status_code == 413 and r.json()["detail"]["code"] == "FILE_TOO_LARGE"

    r = client.post("/owner/shop/photo", headers=h, files={"file": ("a.png", PNG, "image/png")})
    assert r.status_code == 200, r.text
    first = r.json()
    assert first["photo_public_id"].startswith("local:shops/") and "/media/shops/" in first["photo_url"]
    assert client.get(first["photo_url"].replace("http://localhost:8000", "")).status_code == 200
    assert client.get("/owner/shop", headers=h).json()["photo_url"] == first["photo_url"]

    r = client.post("/owner/shop/photo", headers=h, files={"file": ("b.jpg", JPG, "image/jpeg")})
    second = r.json()
    assert second["photo_url"] != first["photo_url"]
    assert client.get(first["photo_url"].replace("http://localhost:8000", "")).status_code == 404  # old asset deleted
    assert client.get(second["photo_url"].replace("http://localhost:8000", "")).status_code == 200


def test_product_crud_price_history_and_soft_delete(owner):
    h = owner["headers"]
    assert client.get("/owner/products", headers=h).status_code == 404  # no shop yet
    client.put("/owner/shop", json=SHOP, headers=h)

    r = client.post("/owner/products", json=PRODUCT, headers=h)
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["price"] == "54.00" and p["stock_qty"] == "10.000" and p["stock_status"] == "in_stock"
    assert p["is_active"] is True and p["aliases"] == ["butter", "makkhan"]

    for bad in [{"price": "0"}, {"price": "-5"}, {"stock_qty": "-1"}, {"pack_size": "0"}, {"pack_unit": "bottle"}]:
        assert client.post("/owner/products", json={**PRODUCT, **bad}, headers=h).status_code == 422, bad

    # price edit writes history; same-price edit and stock edit do not
    assert client.patch(f"/owner/products/{p['id']}", json={"price": "60.00"}, headers=h).json()["price"] == "60.00"
    client.patch(f"/owner/products/{p['id']}", json={"price": "60"}, headers=h)
    r = client.patch(f"/owner/products/{p['id']}", json={"stock_qty": "3"}, headers=h)
    assert r.json()["stock_status"] == "low_stock"
    assert client.patch(f"/owner/products/{p['id']}", json={"stock_qty": "0"}, headers=h).json()["stock_status"] == "out_of_stock"
    assert client.patch(f"/owner/products/{p['id']}", json={"price": None}, headers=h).status_code == 422
    with SessionLocal() as db:
        rows = db.scalars(select(PriceHistory).where(PriceHistory.product_id == p["id"])).all()
        assert len(rows) == 1 and str(rows[0].old_price) == "54.00" and str(rows[0].new_price) == "60.00"

    assert client.get("/owner/products?q=makkhan", headers=h).json()["total"] == 1
    assert client.get("/owner/products?q=zzz", headers=h).json()["total"] == 0

    assert client.delete(f"/owner/products/{p['id']}", headers=h).status_code == 204
    assert client.get("/owner/products", headers=h).json()["total"] == 0
    assert client.get("/owner/products?include_inactive=true", headers=h).json()["total"] == 1
    assert client.patch("/owner/products/99999999", json={"price": "1"}, headers=h).status_code == 404


def test_cannot_touch_another_shops_product(owner):
    client.put("/owner/shop", json=SHOP, headers=owner["headers"])
    pid = client.post("/owner/products", json=PRODUCT, headers=owner["headers"]).json()["id"]

    other = client.post("/auth/owner/signup", json={"name": "O2", "email": f"t{uuid.uuid4().hex[:10]}@test.in", "password": "secret123"})
    h2 = {"Authorization": f"Bearer {other.json()['access_token']}"}
    client.put("/owner/shop", json={**SHOP, "name": "Other Shop"}, headers=h2)
    try:
        assert client.patch(f"/owner/products/{pid}", json={"price": "1"}, headers=h2).status_code == 403
        assert client.delete(f"/owner/products/{pid}", headers=h2).status_code == 403
        assert client.get("/owner/products", headers=h2).json()["total"] == 0  # list never leaks it
    finally:
        with SessionLocal() as db:
            s = db.scalar(select(Shop).where(Shop.name == "Other Shop"))
            o = db.get(Shopkeeper, s.owner_id)
            db.delete(s); db.delete(o); db.commit()


def test_public_shop(owner):
    h = owner["headers"]
    slug = client.put("/owner/shop", json=SHOP, headers=h).json()["slug"]
    client.post("/owner/products", json=PRODUCT, headers=h)
    hidden = client.post("/owner/products", json={**PRODUCT, "name": "Hidden"}, headers=h).json()
    client.delete(f"/owner/products/{hidden['id']}", headers=h)

    r = client.get(f"/shops/{slug}")  # no token
    assert r.status_code == 200
    body = r.json()
    names = [p["name"] for c in body["categories"] for p in c["products"]]
    assert names == ["Amul Butter 100g"]
    assert body["categories"][0]["name"] == "Dairy"
    assert not ({"owner_id", "owner", "email", "phone", "password_hash", "photo_public_id"} & set(body["shop"]))
    assert "is_active" not in body["categories"][0]["products"][0]
    assert client.get("/shops/does-not-exist").status_code == 404


def test_geo_search_cache_and_failure(monkeypatch):
    calls = []

    class Resp:
        def raise_for_status(self): pass
        def json(self):
            return {"status": "OK", "results": [{"formatted_address": "Kothrud, Pune", "geometry": {"location": {"lat": 18.5, "lng": 73.8}}}]}

    def fake_get(url, **kw):
        calls.append(url)
        return Resp()

    monkeypatch.setattr(geo.httpx, "get", fake_get)
    monkeypatch.setattr(get_settings(), "google_maps_api_key", "test-key")
    geo._cache.clear()
    q = f"kothrud {uuid.uuid4().hex[:6]}"
    r = client.get("/geo/search", params={"q": q})
    assert r.json() == [{"display_name": "Kothrud, Pune", "lat": 18.5, "lng": 73.8}]
    client.get("/geo/search", params={"q": q})
    assert len(calls) == 1  # second answer came from the cache
    assert client.get("/geo/search", params={"q": ""}).json() == []

    def boom(url, **kw):
        raise RuntimeError("down")

    monkeypatch.setattr(geo.httpx, "get", boom)
    assert client.get("/geo/search", params={"q": "something else"}).json() == []

    # no key configured: no upstream call at all, still a clean empty list
    monkeypatch.setattr(get_settings(), "google_maps_api_key", "")
    monkeypatch.setattr(geo.httpx, "get", lambda *a, **k: pytest.fail("must not call the geocoder without a key"))
    assert client.get("/geo/search", params={"q": "another place"}).json() == []

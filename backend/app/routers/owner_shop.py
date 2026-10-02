import logging

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import find_owner_shop, get_current_owner, get_owner_shop
from app.errors import api_error
from app.models import Shop, Shopkeeper, Upload
from app.schemas.shop import PhotoOut, ShopIn, ShopOwner
from app.services import storage
from app.services.shops import owner_shop_out
from app.services.slug import unique_slug

log = logging.getLogger("hod.owner_shop")
router = APIRouter(prefix="/owner/shop", tags=["owner shop"])

MAX_PHOTO_BYTES = 5 * 1024 * 1024
ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}
# Name and column are NOT NULL in the database, so an explicit null in the body is ignored for these.
_NOT_NULL = {"name", "min_order_value", "delivery_fee", "is_open"}


def _sniff(head: bytes) -> str | None:
    """Detect the real image type from the file's first bytes, whatever the client claimed."""
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return None


@router.get("", response_model=ShopOwner)
def get_shop(shop: Shop = Depends(get_owner_shop)):
    return owner_shop_out(shop)


@router.put("", response_model=ShopOwner)
def put_shop(
    body: ShopIn,
    owner: Shopkeeper = Depends(get_current_owner),
    db: Session = Depends(get_db),
):
    shop = find_owner_shop(db, owner)
    values = {
        f: getattr(body, f)
        for f in body.model_fields_set
        if not (getattr(body, f) is None and f in _NOT_NULL)
    }
    if shop is None:
        for attempt in range(3):
            shop = Shop(owner_id=owner.id, slug=unique_slug(db, body.name), **values)
            db.add(shop)
            try:
                db.commit()
                break
            except IntegrityError:  # another signup took the slug between check and insert
                db.rollback()
                if attempt == 2:
                    raise api_error(409, "CONFLICT", "Could not create the shop. Please try again.")
    else:
        for f, v in values.items():
            setattr(shop, f, v)  # the slug never changes after creation
        db.commit()
    db.refresh(shop)
    return owner_shop_out(shop)


@router.post("/photo", response_model=PhotoOut)
def upload_photo(
    file: UploadFile = File(...),
    shop: Shop = Depends(get_owner_shop),
    db: Session = Depends(get_db),
):
    if file.content_type not in ALLOWED_MIME:
        raise api_error(400, "FILE_TYPE_NOT_ALLOWED", "Only JPG, PNG or WebP images are allowed.")
    data = file.file.read(MAX_PHOTO_BYTES + 1)
    if len(data) > MAX_PHOTO_BYTES:
        raise api_error(413, "FILE_TOO_LARGE", "Photo must be 5 MB or smaller.")
    mime = _sniff(data[:12])
    if mime is None:
        raise api_error(400, "FILE_TYPE_NOT_ALLOWED", "That file isn't a valid JPG, PNG or WebP image.")

    try:
        url, public_id = storage.upload(data, mime, folder="shops")
    except Exception:
        log.exception("Photo upload failed")
        raise api_error(502, "UPLOAD_FAILED", "Could not store the photo. Please try again.")

    old_public_id = shop.photo_public_id
    shop.photo_url = url
    shop.photo_public_id = public_id
    db.add(Upload(shop_id=shop.id, kind="shop_photo", url=url, public_id=public_id, mime=mime, bytes=len(data)))
    if old_public_id:
        for row in db.query(Upload).filter(Upload.shop_id == shop.id, Upload.public_id == old_public_id):
            db.delete(row)
    db.commit()

    storage.delete(old_public_id)  # best effort, after the new photo is safely saved
    return PhotoOut(photo_url=url, photo_public_id=public_id)

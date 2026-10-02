import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Shop


def slugify(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")[:60].strip("-")
    return slug or "shop"  # e.g. a name written only in Devanagari


def unique_slug(db: Session, name: str) -> str:
    base = slugify(name)
    slug, n = base, 1
    while db.scalar(select(Shop.id).where(Shop.slug == slug)) is not None:
        n += 1
        slug = f"{base}-{n}"
    return slug

from app.models import Shop
from app.schemas.shop import ShopOwner


def is_configured(shop: Shop) -> bool:
    """Name + map location + radius are set (what the owner must finish before ordering works)."""
    return bool(shop.name and shop.lat is not None and shop.lng is not None and shop.delivery_radius_km is not None)


def owner_shop_out(shop: Shop) -> ShopOwner:
    data = {f: getattr(shop, f) for f in ShopOwner.model_fields if f != "is_configured"}
    return ShopOwner(**data, is_configured=is_configured(shop))

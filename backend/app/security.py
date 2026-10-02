from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import get_settings

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
_ALGO = "HS256"
# Verified against when the account doesn't exist, so login timing doesn't reveal which accounts exist.
_DUMMY_HASH = _pwd.hash("not-a-real-password")


def hash_password(password: str) -> str:
    return _pwd.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    if password_hash is None:
        _pwd.verify(password, _DUMMY_HASH)
        return False
    try:
        return _pwd.verify(password, password_hash)
    except ValueError:
        return False


def create_access_token(sub: int, role: str, shop_id: int | None = None) -> str:
    s = get_settings()
    claims: dict = {
        "sub": str(sub),
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=s.jwt_expire_hours),
    }
    if shop_id is not None:
        claims["shop_id"] = shop_id
    return jwt.encode(claims, s.jwt_secret, algorithm=_ALGO)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, get_settings().jwt_secret, algorithms=[_ALGO])
    except JWTError:
        return None

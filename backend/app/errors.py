from fastapi import HTTPException


def api_error(status: int, code: str, message: str, **extra) -> HTTPException:
    """Coded error: {"detail": {"code", "message", ...}} (see API_CONTRACT.md 1.3)."""
    return HTTPException(status_code=status, detail={"code": code, "message": message, **extra})

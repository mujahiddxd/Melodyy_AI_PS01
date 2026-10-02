import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.config import get_settings
from app.db import engine
from app.routers import auth, owner_products, owner_shop, public
from app.services.storage import UPLOAD_DIR

log = logging.getLogger("hod")
settings = get_settings()

app = FastAPI(title="Hinglish Order Desk API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=list({"http://localhost:3000", "http://127.0.0.1:3000", settings.frontend_origin}),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth.router)
app.include_router(owner_shop.router)
app.include_router(owner_products.router)
app.include_router(public.router)

# Local storage fallback for photos (used when CLOUDINARY_URL is empty)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=UPLOAD_DIR), name="media")


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Something went wrong. Please try again."})


@app.get("/health")
def health():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "db": "ok"}
    except Exception:
        log.exception("Health check: database unreachable")
        return JSONResponse(status_code=503, content={"status": "degraded", "db": "error"})

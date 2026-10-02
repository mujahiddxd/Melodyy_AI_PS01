"""Geocoding proxy for the Google Geocoding API. Cached, max 1 upstream request per second.

The Google key lives only in the backend .env and is never logged or returned to the client.
"""
import logging
import threading
import time

import httpx

from app.config import get_settings

log = logging.getLogger("hod.geo")
# httpx logs full request URLs at INFO, which would put the API key into the logs.
logging.getLogger("httpx").setLevel(logging.WARNING)

_CACHE_TTL = 3600.0
_CACHE_MAX = 500
_MIN_INTERVAL = 1.0
_cache: dict[str, tuple[float, list[dict]]] = {}
_warned_no_key: list[bool] = []
_lock = threading.Lock()
_last_call = 0.0


def _google(q: str) -> list[dict]:
    s = get_settings()
    r = httpx.get(
        "https://maps.googleapis.com/maps/api/geocode/json",
        params={"address": q, "region": "in", "key": s.google_maps_api_key.strip()},
        timeout=6.0,
    )
    r.raise_for_status()
    body = r.json()
    status = body.get("status")
    if status == "ZERO_RESULTS":
        return []
    if status != "OK":
        # e.g. REQUEST_DENIED when the Geocoding API isn't enabled or billing is off
        raise RuntimeError(f"Google Geocoding status {status}: {body.get('error_message', '')[:200]}")
    out = []
    for item in body.get("results", [])[:5]:
        loc = item.get("geometry", {}).get("location", {})
        if "lat" in loc and "lng" in loc:
            out.append({"display_name": item.get("formatted_address", ""), "lat": float(loc["lat"]), "lng": float(loc["lng"])})
    return out


def search(q: str) -> list[dict]:
    """Returns [{display_name, lat, lng}]. Any provider failure returns [] so map click and GPS still work."""
    global _last_call
    q = " ".join(q.split())[:200]
    if len(q) < 2:
        return []
    if not get_settings().google_maps_api_key.strip():
        if not _warned_no_key:
            log.warning("GOOGLE_MAPS_API_KEY is not set: /geo/search returns no results")
            _warned_no_key.append(True)
        return []
    key = q.lower()

    with _lock:
        hit = _cache.get(key)
        if hit and time.monotonic() - hit[0] < _CACHE_TTL:
            return hit[1]
        wait = _MIN_INTERVAL - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.monotonic()
        try:
            results = _google(q)
        except Exception as e:
            # log the reason only; the exception text could contain the request URL for transport errors
            log.warning("Geocoder failed: %s", type(e).__name__ if not isinstance(e, RuntimeError) else e)
            return []
        results = [{"display_name": r["display_name"], "lat": r["lat"], "lng": r["lng"]} for r in results]
        if len(_cache) >= _CACHE_MAX:
            _cache.clear()
        _cache[key] = (time.monotonic(), results)
        return results

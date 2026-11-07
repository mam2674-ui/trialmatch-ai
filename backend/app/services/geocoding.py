"""Patient-location geocoding and distance computation.

Only the coarse place the user typed (city/state/postal code/country) is sent to the geocoder, never any
clinical information. Trial-site coordinates are never geocoded by us: they come from ClinicalTrials.gov's
own `geoPoint`. Distances are only reported when both ends have real coordinates.
"""

from __future__ import annotations

import asyncio
import math
import time

import httpx

from app.core.config import get_settings
from app.schemas.patient import Location

_cache: dict[str, tuple[float, float, str] | None] = {}
_lock = asyncio.Lock()
_last_call = 0.0


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 3958.7613
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


async def geocode(location: Location, http: httpx.AsyncClient | None = None) -> Location:
    """Return a copy of `location` with lat/lon set if the geocoder resolved it; otherwise unchanged."""
    s = get_settings()
    if not location.known or s.geocoder == "none":
        return location
    if location.lat is not None and location.lon is not None:
        return location
    q = location.query_string()
    key = q.lower()
    if key not in _cache:
        _cache[key] = await _nominatim(location, s.geocoder_user_agent, http)
    hit = _cache[key]
    if hit is None:
        return location
    lat, lon, label = hit
    return location.model_copy(update={"lat": lat, "lon": lon, "geocoded_label": label})


async def _nominatim(loc: Location, ua: str, http: httpx.AsyncClient | None) -> tuple[float, float, str] | None:
    global _last_call
    params = {"format": "json", "limit": 1, "addressdetails": 0}
    structured = {k: v for k, v in {"city": loc.city, "state": loc.state, "postalcode": loc.postal_code,
                                     "country": loc.country}.items() if v}
    if len(structured) == 1 and loc.city:
        params["q"] = loc.city  # free-form works better for "Boston" alone
    else:
        params.update(structured)
    async with _lock:  # Nominatim usage policy: max 1 request/second
        wait = 1.0 - (time.monotonic() - _last_call)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_call = time.monotonic()
        client = http or httpx.AsyncClient(timeout=10, headers={"User-Agent": ua})
        try:
            resp = await client.get("https://nominatim.openstreetmap.org/search", params=params)
            if resp.status_code != 200:
                return None
            data = resp.json()
        except (httpx.HTTPError, ValueError):
            return None
        finally:
            if http is None:
                await client.aclose()
    if not data:
        return None
    return float(data[0]["lat"]), float(data[0]["lon"]), data[0].get("display_name", "")

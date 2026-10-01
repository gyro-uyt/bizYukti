"""PostGIS helpers and locality resolution."""

import logging
import math
import uuid

import httpx
from sqlalchemy import func, literal_column, select
from sqlalchemy.orm import Session

from .config import settings
from .models import OpportunityArea

log = logging.getLogger("bizyukti.geo")


def point(lat: float, lng: float):
    """geography point bound as parameters (never string-formatted)."""
    return func.geography(func.ST_SetSRID(func.ST_MakePoint(lng, lat), 4326))


def geog(table: str):
    return literal_column(f"{table}.geog")


def within(table: str, lat: float, lng: float, meters: float):
    return func.ST_DWithin(geog(table), point(lat, lng), meters)


def distance(table: str, lat: float, lng: float):
    return func.ST_Distance(geog(table), point(lat, lng))


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearest_area(db: Session, lat: float, lng: float, slack: float = 1.6) -> tuple[OpportunityArea | None, float | None]:
    dist = distance("opportunity_areas", lat, lng)
    row = db.execute(
        select(OpportunityArea, dist.label("d")).order_by(dist).limit(1)
    ).first()
    if not row:
        return None, None
    area, d = row
    return (area, float(d)) if d <= area.radius_m * slack else (None, float(d))


def _nominatim(lat: float, lng: float) -> tuple[str | None, str | None]:
    try:
        r = httpx.get(
            f"{settings.nominatim_url}/reverse",
            params={"lat": lat, "lon": lng, "format": "jsonv2", "zoom": 16},
            headers={"User-Agent": f"{settings.app_name}/1.0 ({settings.public_web_url})"},
            timeout=4,
        )
        r.raise_for_status()
        addr = r.json().get("address", {})
        locality = addr.get("suburb") or addr.get("neighbourhood") or addr.get("city_district") or addr.get("village")
        city = addr.get("city") or addr.get("town") or addr.get("state_district")
        return locality, city
    except Exception as exc:  # network issues must never block a user action
        log.warning("reverse geocode failed: %s", exc)
        return None, None


def resolve_locality(db: Session, lat: float, lng: float) -> dict:
    area, d = nearest_area(db, lat, lng)
    if area:
        return {"locality": area.name, "city": area.city, "area_id": area.id, "distance_m": round(d or 0)}
    locality = city = None
    if settings.geocoder == "nominatim":
        locality, city = _nominatim(lat, lng)
    return {
        "locality": locality or f"Near {lat:.3f}, {lng:.3f}",
        "city": city or settings.default_city,
        "area_id": None,
        "distance_m": None,
    }


def area_id_for(db: Session, lat: float, lng: float) -> uuid.UUID | None:
    area, _ = nearest_area(db, lat, lng)
    return area.id if area else None

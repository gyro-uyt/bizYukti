"""Static product configuration, the category list, and places (areas, reverse geocode, local demand context)."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .. import taxonomy
from ..config import settings
from ..db import get_db
from ..geo import resolve_locality
from ..models import OpportunityArea
from ..serializers import area_out
from ..services import matching, rewards

router = APIRouter(tags=["meta"])


@router.get("/meta/config")
def config(db: Session = Depends(get_db)):
    cities = db.scalars(select(OpportunityArea.city).distinct().order_by(OpportunityArea.city)).all()
    return {
        "app_name": settings.app_name,
        "default_city": settings.default_city,
        "default_center": {"lat": settings.default_lat, "lng": settings.default_lng},
        "cities": list(cities) or [settings.default_city],
        "reasons": [{"slug": k, "label": v} for k, v in taxonomy.REASONS.items()],
        "property_types": [{"slug": k, "label": v} for k, v in taxonomy.PROPERTY_TYPES.items()],
        "amenities": [{"slug": k, "label": v} for k, v in taxonomy.AMENITIES.items()],
        "rewards": {"demand_max_points": rewards.DEMAND_MAX_POINTS,
                    "tiers": [{"name": n, "at": t} for n, t in rewards.TIERS]},
        "trust": {"local_radius_km": settings.local_radius_km,
                  "verify_min_supporters": settings.demand_verify_min_supporters,
                  "growing_threshold": settings.growing_threshold},
    }


@router.get("/meta/categories")
def categories():
    return taxonomy.public_list()


@router.get("/geo/reverse")
def reverse(lat: float = Query(ge=-90, le=90), lng: float = Query(ge=-180, le=180), db: Session = Depends(get_db)):
    loc = resolve_locality(db, lat, lng)
    return {**loc, "area_id": str(loc["area_id"]) if loc["area_id"] else None, "lat": lat, "lng": lng}


@router.get("/geo/areas")
def areas(city: str | None = None, q: str | None = Query(default=None, max_length=80), db: Session = Depends(get_db)):
    stmt = select(OpportunityArea).order_by(OpportunityArea.city, OpportunityArea.name)
    if city:
        stmt = stmt.where(func.lower(OpportunityArea.city) == city.lower())
    if q:
        stmt = stmt.where(OpportunityArea.name.ilike(f"%{q.strip()}%") | OpportunityArea.city.ilike(f"%{q.strip()}%"))
    return [area_out(a) for a in db.scalars(stmt.limit(100))]


_CONTEXT_SQL = text("""
SELECT d.category, COUNT(*) AS demands, COALESCE(SUM(d.verified_support_count), 0) AS supporters,
       (ARRAY_AGG(d.id ORDER BY d.verified_support_count DESC))[1] AS top_id
FROM demands d
WHERE d.status IN ('published', 'growing', 'matched')
  AND ST_DWithin(d.geog, ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography, :r)
GROUP BY d.category ORDER BY supporters DESC LIMIT 6""")


@router.get("/geo/demand-context")
def demand_context(lat: float = Query(ge=-90, le=90), lng: float = Query(ge=-180, le=180),
                   radius_m: int = Query(default=2000, ge=200, le=10000), db: Session = Depends(get_db)):
    """What nearby residents are asking for: shown while listing a space (P2) and on area pages."""
    rows = db.execute(_CONTEXT_SQL, {"lat": lat, "lng": lng, "r": radius_m}).all()
    label, total = matching.density_label(db, lat, lng, radius_m)
    top = [{"category": r.category, "category_name": taxonomy.get(r.category).name, "demands": int(r.demands),
            "supporters": int(r.supporters), "top_demand_id": str(r.top_id),
            "suits": list(taxonomy.get(r.category).types)} for r in rows]
    return {"density": label, "supporters": total, "radius_m": radius_m, "top": top,
            "locality": resolve_locality(db, lat, lng)["locality"]}

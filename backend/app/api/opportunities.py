"""Business discovery: where should we open, and what space already exists there (B1-B3)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import taxonomy
from ..config import settings
from ..db import get_db
from ..events import emit
from ..geo import distance, haversine_m, within
from ..models import BusinessProfile, Inquiry, OpportunityArea, Property, SavedItem, User
from ..security import current_user, optional_user
from ..serializers import demand_out, property_out
from ..services import matching
from ..services import opportunities as svc
from .deps import get_or_404

router = APIRouter(tags=["opportunities"])


def _profile(db: Session, user: User | None) -> BusinessProfile | None:
    return db.scalar(select(BusinessProfile).where(BusinessProfile.user_id == user.id)) if user else None


def _defaults(db: Session, user: User | None, category: str | None, city: str | None, budget: int | None):
    profile = _profile(db, user)
    cat = category if category in taxonomy.BY_SLUG else (profile.categories[0] if profile and profile.categories else "pharmacy")
    town = city or (profile.preferred_cities[0] if profile and profile.preferred_cities else settings.default_city)
    if budget is None and profile and profile.budget_max:
        budget = profile.budget_max
    return cat, town, budget, profile


@router.get("/opportunities")
def list_opportunities(category: str | None = None, city: str | None = None, budget: int | None = Query(default=None, ge=0),
                       size_min: float | None = Query(default=None, ge=0), size_max: float | None = Query(default=None, ge=0),
                       lat: float | None = Query(default=None, ge=-90, le=90), lng: float | None = Query(default=None, ge=-180, le=180),
                       radius_km: float = Query(default=3, gt=0, le=50),
                       user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    cat, town, budget, profile = _defaults(db, user, category, city, budget)
    result = svc.opportunities(db, cat, town, budget, size_min or (profile.size_min_sqft if profile else None),
                               size_max or (profile.size_max_sqft if profile else None))
    result["near"] = None
    if lat is not None and lng is not None:
        # Target location chosen: keep areas whose centre is within the radius (ranking order unchanged).
        # If none are that close, keep the whole city so the screen is never empty.
        close = [a for a in result["areas"] if haversine_m(lat, lng, a["area"]["lat"], a["area"]["lng"]) <= radius_km * 1000]
        if close:
            result["areas"] = close
            result["strong_demand_areas"] = sum(1 for a in close if a["supporters"] >= svc.STRONG_DEMAND)
        result["near"] = {"radius_km": radius_km, "all": not close}
    saved = set()
    if user:
        saved = {r for r in db.scalars(select(SavedItem.ref_id).where(
            SavedItem.user_id == user.id, SavedItem.kind == "area", SavedItem.category == cat))}
    for a in result["areas"]:
        a["saved"] = uuid.UUID(a["area"]["id"]) in saved
    result["budget"] = budget
    return result


@router.get("/opportunities/areas/{area_id}")
def area_detail(area_id: uuid.UUID, category: str | None = None, budget: int | None = Query(default=None, ge=0),
                user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    """B2: demand + supply + competition + access, ending in one next step."""
    area = get_or_404(db, OpportunityArea, area_id, "Area not found.")
    cat_slug, _, budget, _ = _defaults(db, user, category, area.city, budget)
    cat = taxonomy.get(cat_slug)
    full = svc.opportunities(db, cat.slug, area.city, budget)
    summary = next((a for a in full["areas"] if a["area"]["id"] == str(area.id)), None)
    rank = next((i + 1 for i, a in enumerate(full["areas"]) if a["area"]["id"] == str(area.id)), None)
    spaces = svc.area_spaces(db, area, cat.slug, budget)
    demands = svc.area_demands(db, area, cat.slug)
    saved = bool(user and db.scalar(select(SavedItem.id).where(
        SavedItem.user_id == user.id, SavedItem.kind == "area", SavedItem.ref_id == area.id, SavedItem.category == cat.slug)))
    brief = bool(user and db.scalar(select(Inquiry.id).where(
        Inquiry.from_user_id == user.id, Inquiry.kind == "market_brief", Inquiry.area_id == area.id,
        Inquiry.category == cat.slug)))
    if user:
        emit(db, "opportunity.viewed", user.id, "area", area.id, {"category": cat.slug})
        db.commit()
    return {
        **(summary or {}), "rank": rank, "of": len(full["areas"]),
        "series": svc.weekly_support_series(db, area, cat.slug),
        "demands": [demand_out(d) for d in demands],
        "spaces": [{**property_out(p, distance_m=d), "fit": round(f, 2),
                    "availability_text": matching.availability_text(p)} for p, d, f in spaces],
        "saved": saved, "brief_requested": brief, "budget": budget,
        "categories": [{"slug": c["slug"], "name": c["name"]} for c in taxonomy.public_list()],
    }


@router.get("/map/layers")
def layers(lat: float | None = Query(default=None, ge=-90, le=90), lng: float | None = Query(default=None, ge=-180, le=180),
           radius_km: float = Query(default=8, gt=0, le=40), category: str | None = None,
           budget: int | None = Query(default=None, ge=0), size_min: float | None = Query(default=None, ge=0),
           size_max: float | None = Query(default=None, ge=0), user: User | None = Depends(optional_user),
           db: Session = Depends(get_db)):
    """B3: demand zones (clustered) + available spaces, filterable by category, budget, size and radius."""
    clat = lat if lat is not None else (user.home_lat if user and user.home_lat is not None else settings.default_lat)
    clng = lng if lng is not None else (user.home_lng if user and user.home_lng is not None else settings.default_lng)
    cat = category if category in taxonomy.BY_SLUG else None
    zones = svc.demand_zones(db, clat, clng, radius_km * 1000, cat)
    dist = distance("properties", clat, clng).label("d")
    stmt = select(Property, dist).where(Property.status == "published", within("properties", clat, clng, radius_km * 1000))
    if cat:
        lo, hi = taxonomy.size_window(cat)
        stmt = stmt.where(Property.type.in_(taxonomy.get(cat).types))
        size_min, size_max = size_min or lo, size_max or hi
    if size_min:
        stmt = stmt.where((Property.size_sqft.is_(None)) | (Property.size_sqft >= size_min))
    if size_max:
        stmt = stmt.where((Property.size_sqft.is_(None)) | (Property.size_sqft <= size_max))
    if budget:
        stmt = stmt.where((Property.price_type != "rent") | (Property.price_amount.is_(None)) | (Property.price_amount <= budget))
    spaces = db.execute(stmt.order_by(dist).limit(300)).all()
    areas = db.scalars(select(OpportunityArea).where(within("opportunity_areas", clat, clng, radius_km * 1000 + 2000))).all()
    return {
        "center": {"lat": clat, "lng": clng}, "radius_km": radius_km, "category": cat,
        "zones": zones,
        "spaces": [{"id": str(p.id), "lat": p.lat, "lng": p.lng, "title": property_out(p)["display_title"],
                    "type": p.type, "size_sqft": p.size_sqft, "price_type": p.price_type, "price_amount": p.price_amount,
                    "price_negotiable": p.price_negotiable, "locality": p.locality,
                    "verified": p.verification_status == "verified", "distance_m": round(float(d)),
                    "cover_url": property_out(p)["cover_url"]} for p, d in spaces],
        "areas": [{"id": str(a.id), "name": a.name, "lat": a.lat, "lng": a.lng, "radius_m": a.radius_m} for a in areas],
    }

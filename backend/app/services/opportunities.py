"""Business opportunity intelligence (each demand counts toward exactly one area, so overlapping
catchments never double count): where does demand + available space + manageable
competition already exist? Output is always a label plus reasons, never a bare score."""

from datetime import timedelta

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .. import taxonomy
from ..geo import distance, within
from ..models import Demand, OpportunityArea, Property
from ..security import utcnow

LIVE = "('published','growing','matched')"
STRONG_DEMAND = 20


def _params(category: str, city: str, budget: int | None, size_min: float | None, size_max: float | None) -> dict:
    lo, hi = taxonomy.size_window(category)
    return {"cat": category, "city": city, "types": list(taxonomy.get(category).types),
            "smin": float(size_min) if size_min else lo, "smax": float(size_max) if size_max else hi,
            "budget": budget}


_DEMAND_SQL = text(f"""
SELECT a.id, COALESCE(SUM(d.verified_support_count), 0) AS supporters, COUNT(d.id) AS demands
FROM opportunity_areas a
LEFT JOIN demands d ON d.category = :cat AND d.status IN {LIVE} AND d.area_id = a.id
WHERE a.city = :city GROUP BY a.id""")

_SUPPLY_SQL = text("""
SELECT a.id, COUNT(p.id) AS spaces
FROM opportunity_areas a
LEFT JOIN properties p ON p.status = 'published' AND p.type = ANY(:types)
  AND ST_DWithin(p.geog, a.geog, a.radius_m)
  AND (p.size_sqft IS NULL OR p.size_sqft BETWEEN CAST(:smin AS float8) AND CAST(:smax AS float8))
  AND (CAST(:budget AS bigint) IS NULL OR p.price_type <> 'rent' OR p.price_amount IS NULL
       OR p.price_amount <= CAST(:budget AS bigint))
WHERE a.city = :city GROUP BY a.id""")

_TREND_SQL = text(f"""
SELECT a.id,
  COUNT(s.id) FILTER (WHERE s.created_at >= now() - interval '14 days') AS recent,
  COUNT(s.id) FILTER (WHERE s.created_at < now() - interval '14 days' AND s.created_at >= now() - interval '28 days') AS prior
FROM opportunity_areas a
JOIN demands d ON d.category = :cat AND d.status IN {LIVE} AND d.area_id = a.id
JOIN demand_supports s ON s.demand_id = d.id AND s.status = 'verified'
WHERE a.city = :city GROUP BY a.id""")


def _trend(recent: int, prior: int) -> dict:
    if recent == 0 and prior == 0:
        return {"direction": "quiet", "change_pct": 0, "text": "No new support in the last month"}
    if prior == 0:
        return {"direction": "new", "change_pct": 100, "text": f"{recent} new supporters in two weeks"}
    pct = round((recent - prior) / prior * 100)
    if pct >= 15:
        return {"direction": "rising", "change_pct": pct, "text": f"Up {pct}% in the last two weeks"}
    if pct <= -15:
        return {"direction": "cooling", "change_pct": pct, "text": f"Down {abs(pct)}% in the last two weeks"}
    return {"direction": "steady", "change_pct": pct, "text": "Steady over the last month"}


def _plural(cat: taxonomy.Category, n: int) -> str:
    name = cat.name.lower()
    if n == 1 or name.endswith("s"):
        return name
    if name.endswith("y") and name[-2:-1] not in "aeiou":
        return name[:-1] + "ies"  # pharmacy -> pharmacies
    return name + "s"


def score_area(cat: taxonomy.Category, area: OpportunityArea, supporters: int, demands: int, spaces: int,
               recent: int, prior: int, budget_applied: bool) -> dict:
    stats = area.stats or {}
    competitors = int((stats.get("competition") or {}).get(cat.slug, 0))
    access = stats.get("access") or {}
    footfall = float(access.get("footfall_index", 0.5))
    demand_s = taxonomy.demand_strength(supporters, 150)
    supply_s = min(1.0, spaces / 4)
    competition_s = 1 / (1 + competitors / 3)
    total = 0.45 * demand_s + 0.25 * supply_s + 0.15 * footfall + 0.15 * competition_s
    if total >= 0.62 and supporters >= STRONG_DEMAND:
        label, tone = "Strong opportunity", "strong"
    elif total >= 0.42:
        label, tone = "Promising", "promising"
    else:
        label, tone = "Early signal", "early"
    trend = _trend(recent, prior)

    reasons = []
    if supporters:
        reasons.append(f"{supporters:,} verified residents want {cat.noun} here" +
                       (f" — {trend['text'].lower()}" if trend["direction"] in ("rising", "new") else ""))
    else:
        reasons.append(f"No verified requests for {cat.noun} here yet")
    if spaces:
        reasons.append(f"{spaces} available space{'s' if spaces > 1 else ''} fit {cat.name.lower()} needs"
                       + (" within your budget" if budget_applied else ""))
    else:
        reasons.append("No matching spaces listed yet")
    if competitors == 0:
        reasons.append(f"No existing {cat.name.lower()} recorded nearby")
    else:
        level = "light" if competitors <= 2 else "moderate" if competitors <= 5 else "heavy"
        reasons.append(f"{competitors} existing {_plural(cat, competitors)} nearby — {level} competition")
    if access.get("notes"):
        reasons.append(access["notes"])
    return {
        "area": {"id": str(area.id), "name": area.name, "city": area.city, "lat": area.lat, "lng": area.lng,
                 "radius_m": area.radius_m},
        "category": cat.slug, "category_name": cat.name,
        "label": label, "tone": tone, "score": round(total, 3),
        "supporters": supporters, "demands": demands, "spaces": spaces, "competitors": competitors,
        "trend": trend,
        "access": {"transit": access.get("transit", "medium"), "road": access.get("road"),
                   "footfall_index": footfall, "notes": access.get("notes")},
        "reasons": reasons,
    }


def opportunities(db: Session, category: str, city: str, budget: int | None = None,
                  size_min: float | None = None, size_max: float | None = None) -> dict:
    cat = taxonomy.get(category)
    params = _params(cat.slug, city, budget, size_min, size_max)
    areas = {a.id: a for a in db.scalars(select(OpportunityArea).where(OpportunityArea.city == city))}
    demand = {r.id: r for r in db.execute(_DEMAND_SQL, params)}
    supply = {r.id: r.spaces for r in db.execute(_SUPPLY_SQL, params)}
    trend = {r.id: (r.recent, r.prior) for r in db.execute(_TREND_SQL, params)}
    results = []
    for aid, area in areas.items():
        d = demand.get(aid)
        recent, prior = trend.get(aid, (0, 0))
        results.append(score_area(cat, area, int(d.supporters) if d else 0, int(d.demands) if d else 0,
                                  int(supply.get(aid, 0)), int(recent), int(prior), budget is not None))
    results.sort(key=lambda r: (r["score"], r["supporters"]), reverse=True)
    return {
        "category": cat.slug, "category_name": cat.name, "city": city,
        "strong_demand_areas": sum(1 for r in results if r["supporters"] >= STRONG_DEMAND),
        "areas": results,
    }


def weekly_support_series(db: Session, area: OpportunityArea, category: str, weeks: int = 8) -> list[dict]:
    rows = db.execute(text(f"""
        SELECT date_trunc('week', s.created_at) AS wk, COUNT(s.id) AS n
        FROM demands d JOIN demand_supports s ON s.demand_id = d.id AND s.status = 'verified'
        WHERE d.category = :cat AND d.status IN {LIVE} AND d.area_id = :area
          AND s.created_at >= now() - make_interval(weeks => :weeks)
        GROUP BY wk ORDER BY wk"""), {"cat": category, "area": area.id, "weeks": weeks}).all()
    counts = {r.wk.date(): int(r.n) for r in rows}
    today = utcnow().date()
    start = today - timedelta(days=today.weekday())
    series = []
    for i in range(weeks - 1, -1, -1):
        wk = start - timedelta(weeks=i)
        series.append({"week": wk.isoformat(), "supporters": counts.get(wk, 0)})
    return series


def area_demands(db: Session, area: OpportunityArea, category: str, limit: int = 5) -> list[Demand]:
    return list(db.scalars(select(Demand).where(
        Demand.category == category, Demand.status.in_(("published", "growing", "matched")),
        Demand.area_id == area.id).order_by(Demand.verified_support_count.desc()).limit(limit)))


def area_spaces(db: Session, area: OpportunityArea, category: str, budget: int | None = None,
                limit: int = 12) -> list[tuple[Property, float, float]]:
    """Returns (property, distance from area centre, fit 0..1) best-first."""
    lo, hi = taxonomy.size_window(category)
    dist = distance("properties", area.lat, area.lng)
    q = select(Property, dist.label("d")).where(
        Property.status == "published", Property.type.in_(taxonomy.get(category).types),
        within("properties", area.lat, area.lng, area.radius_m * 1.3))
    rows = db.execute(q).all()
    out = []
    for prop, d in rows:
        if prop.size_sqft and not (lo <= prop.size_sqft <= hi):
            continue
        if budget and prop.price_type == "rent" and prop.price_amount and prop.price_amount > budget:
            continue
        t, s = taxonomy.suitability(category, prop.type, prop.size_sqft)
        out.append((prop, float(d), t * s))
    out.sort(key=lambda x: (x[2], -x[1]), reverse=True)
    return out[:limit]


def demand_zones(db: Session, lat: float, lng: float, radius_m: float, category: str | None = None,
                 eps_m: float = 700) -> list[dict]:
    """PostGIS DBSCAN clustering of live demand into zones (weighted by verified supporters)."""
    import math
    eps_3857 = eps_m / max(math.cos(math.radians(lat)), 0.2)
    rows = db.execute(text(f"""
        WITH pts AS (
          SELECT d.id, d.category, d.lat, d.lng, GREATEST(d.verified_support_count, 1) AS w, d.verified_support_count AS v,
            ST_ClusterDBSCAN(ST_Transform(d.geog::geometry, 3857), eps := CAST(:eps AS float8), minpoints := 1)
              OVER (PARTITION BY d.category) AS cid
          FROM demands d
          WHERE d.status IN {LIVE}
            AND ST_DWithin(d.geog, ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography, :r)
            AND (CAST(:cat AS text) IS NULL OR d.category = CAST(:cat AS text))
        )
        SELECT category, cid, COUNT(*) AS demands, SUM(v) AS supporters,
               SUM(lat * w) / SUM(w) AS clat, SUM(lng * w) / SUM(w) AS clng,
               (ARRAY_AGG(id ORDER BY v DESC))[1] AS top_id
        FROM pts GROUP BY category, cid ORDER BY supporters DESC LIMIT 200"""),
        {"eps": eps_3857, "lat": lat, "lng": lng, "r": radius_m, "cat": category}).all()
    zones = []
    for r in rows:
        supporters = int(r.supporters or 0)
        cat = taxonomy.get(r.category)
        zones.append({
            "category": r.category, "category_name": cat.name, "demands": int(r.demands),
            "supporters": supporters, "lat": float(r.clat), "lng": float(r.clng),
            "radius_m": int(min(1200, 280 + 55 * math.sqrt(supporters))),
            "intensity": round(taxonomy.demand_strength(supporters), 3), "top_demand_id": str(r.top_id),
        })
    return zones

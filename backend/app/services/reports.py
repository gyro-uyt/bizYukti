"""Business decision reports for people planning a new outlet.

1. Competitor gap analysis: how much verified demand exists for a business type versus how many
   outlets already serve it, compared with the city average and with nearby areas, plus what
   residents say is missing.
2. Financial feasibility: a steady-state monthly P&L, break-even point, setup cost, 36-month cash
   curve with a launch ramp, three demand scenarios, and a Feasible / Marginal / Not feasible status.

Everything is explainable. Demand comes from verified BizYukti supporters; competitor counts and
footfall come from area data; costs come from editable category benchmarks (typical tier-2 Indian
city values). Outputs are planning estimates, never guarantees."""

import math
import re
import statistics
import uuid
from dataclasses import dataclass, replace

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import taxonomy
from ..geo import haversine_m, nearest_area, within
from ..models import BusinessProfile, Demand, OpportunityArea, Property

LIVE = ("published", "growing", "matched")
PROPERTY_CATCHMENT_M = 2000
NEIGHBOUR_RADIUS_M = 5000


# ---------------------------------------------------------------- benchmarks
@dataclass(frozen=True)
class Benchmark:
    ticket: int                 # average bill (retail) or monthly fee per member (subscription), INR
    margin: float               # gross margin after cost of goods sold
    per_supporter: float        # monthly purchases (or sign-ups) per potential customer
    walkins: int                # monthly purchases from passing footfall at footfall index 1.0
    staff: int
    salary: int                 # per person per month, INR
    fitout: int                 # per sq ft, INR
    utilities: float            # per sq ft per month, INR
    other: int                  # other monthly running costs, INR
    inventory: int              # opening stock or equipment, INR
    model: str = "retail"       # retail: customers a day; subscription: paying members
    capacity_sqft: float | None = None  # sq ft per member, caps subscription capacity
    fixed_capacity: int | None = None   # hard cap per month (e.g. turf booking slots)


BENCHMARKS: dict[str, Benchmark] = {
    "pharmacy": Benchmark(350, 0.22, 2.0, 1500, 2, 12000, 450, 10, 8000, 300000),
    "grocery": Benchmark(450, 0.16, 5.0, 2400, 3, 12000, 500, 10, 10000, 450000),
    "cafe": Benchmark(220, 0.65, 2.5, 3000, 4, 13000, 1600, 22, 15000, 60000),
    "restaurant": Benchmark(650, 0.60, 1.2, 1500, 8, 13000, 2000, 28, 25000, 120000),
    "bakery": Benchmark(180, 0.55, 3.5, 2400, 3, 12000, 1300, 28, 10000, 60000),
    "gym": Benchmark(1200, 0.92, 0.5, 40, 3, 12000, 1200, 20, 20000, 1000000, "subscription", capacity_sqft=5),
    "salon": Benchmark(350, 0.75, 1.0, 600, 4, 13000, 1500, 22, 10000, 80000),
    "clinic": Benchmark(500, 0.85, 0.5, 300, 3, 18000, 1300, 18, 15000, 150000),
    "diagnostics": Benchmark(900, 0.60, 0.4, 240, 4, 16000, 1800, 28, 20000, 1200000),
    "coaching": Benchmark(2500, 0.90, 0.25, 10, 4, 20000, 700, 12, 15000, 100000, "subscription", capacity_sqft=10),
    "daycare": Benchmark(6000, 0.85, 0.12, 4, 5, 12000, 1100, 15, 15000, 150000, "subscription", capacity_sqft=35),
    "bookstore": Benchmark(400, 0.30, 0.8, 600, 2, 12000, 800, 10, 8000, 350000),
    "hardware": Benchmark(700, 0.22, 0.6, 750, 3, 12000, 450, 8, 8000, 550000),
    "electronics": Benchmark(800, 0.30, 0.5, 600, 2, 13000, 1100, 15, 8000, 250000),
    "laundry": Benchmark(250, 0.70, 2.0, 240, 3, 11000, 900, 35, 8000, 350000),
    "bank_atm": Benchmark(17, 0.90, 6.0, 1800, 1, 10000, 300, 60, 12000, 600000),
    "pet_care": Benchmark(600, 0.45, 1.0, 180, 2, 13000, 1100, 15, 8000, 200000),
    "coworking": Benchmark(6500, 0.75, 0.2, 10, 2, 15000, 1400, 15, 20000, 700000, "subscription", capacity_sqft=50),
    "sports": Benchmark(1200, 0.85, 0.5, 60, 3, 12000, 150, 4, 15000, 300000, "subscription", fixed_capacity=480),
    "delivery_hub": Benchmark(500, 0.18, 4.0, 0, 6, 13000, 400, 14, 30000, 550000),
    "other": Benchmark(400, 0.40, 1.0, 600, 2, 12000, 1000, 15, 10000, 200000),
}

REACH = 6               # potential customers each verified supporter stands for
DEPOSIT_MONTHS = 6      # security deposit on a commercial lease
LICENCES = 50000        # registration, licences and launch marketing
LOAN_SHARE, LOAN_RATE, LOAN_YEARS = 0.8, 0.095, 15
RAMP = [0.45, 0.55, 0.65, 0.75, 0.85, 0.92]  # share of steady-state sales in launch months 1-6
HORIZON = 36            # months shown in the cash chart
PAYBACK_LIMIT = 120     # beyond 10 years the setup cost is treated as never earned back
SCENARIOS = [("conservative", "Conservative", 0.7), ("expected", "Expected", 1.0), ("optimistic", "Optimistic", 1.3)]

# Businesses that bring customers to each other (their presence nearby helps, not hurts).
COMPLEMENTS: dict[str, list[str]] = {
    "pharmacy": ["clinic", "diagnostics"], "clinic": ["pharmacy", "diagnostics"], "diagnostics": ["clinic", "pharmacy"],
    "cafe": ["coworking", "coaching", "bookstore", "gym"], "coworking": ["cafe", "bank_atm"], "coaching": ["bookstore", "cafe"],
    "bookstore": ["coaching", "cafe"], "grocery": ["bakery", "pharmacy"], "bakery": ["grocery", "cafe"], "gym": ["cafe", "salon"],
    "salon": ["gym", "cafe"], "restaurant": ["cafe", "bakery"], "daycare": ["coaching", "clinic"], "laundry": ["grocery"],
    "hardware": ["electronics"], "electronics": ["hardware", "bank_atm"], "pet_care": ["pharmacy"], "bank_atm": ["grocery", "pharmacy"],
    "sports": ["cafe", "gym"], "delivery_hub": ["grocery"],
}

# What residents say is missing, read from request wording (weighted by verified supporters).
SERVICE_GAPS: list[tuple[str, re.Pattern]] = [
    ("Longer opening hours", re.compile(r"\b(late|night|24[\s-]?(hour|hr|x7|/7)s?|all day|open till)\b", re.I)),
    ("Women-focused", re.compile(r"\b(women|ladies|female)\b", re.I)),
    ("For children", re.compile(r"\b(child|children|children's|kids|pediatric|paediatric)\b", re.I)),
    ("Family-friendly", re.compile(r"\bfamil(y|ies)\b", re.I)),
    ("Space to sit and work", re.compile(r"\b(quiet|seating|work from|wifi|laptop)\b", re.I)),
    ("Exam preparation", re.compile(r"\b(competitive|exam|exams|jee|neet|upsc)\b", re.I)),
    ("Fresh produce", re.compile(r"\b(fresh|vegetable|vegetables|fruit|fruits|organic)\b", re.I)),
    ("Affordable prices", re.compile(r"\b(cheap|affordable|budget|low cost)\b", re.I)),
    ("Home delivery", re.compile(r"\b(delivery|deliver)\b", re.I)),
    ("Specialist care", re.compile(r"\b(dental|dentist|eye|skin|physio)\b", re.I)),
]


# ---------------------------------------------------------------- scope helpers
def resolve_scope(db: Session, area_id: uuid.UUID | None, property_id: uuid.UUID | None, viewer_id: uuid.UUID | None,
                  is_admin: bool = False) -> tuple[OpportunityArea, Property | None]:
    prop = None
    if property_id:
        prop = db.get(Property, property_id)
        if not prop or (prop.status != "published" and not (is_admin or prop.owner_id == viewer_id)):
            raise HTTPException(404, "This space isn't available.")
        if prop.lat is None or prop.lng is None:
            raise HTTPException(422, "This space has no location yet, so it can't be analysed.")
        area = db.get(OpportunityArea, prop.area_id) if prop.area_id else None
        area = area or nearest_area(db, prop.lat, prop.lng, slack=10)[0]
    else:
        area = db.get(OpportunityArea, area_id) if area_id else None
    if not area:
        raise HTTPException(404, "Area not found.")
    return area, prop


def default_category(db: Session, profile: BusinessProfile | None, prop: Property | None, area: OpportunityArea) -> str:
    """The business's own category when it suits the space, else the strongest local demand the space can host."""
    cats = [c for c in (profile.categories if profile else []) if c in taxonomy.BY_SLUG]
    if prop:
        fitting = [c for c in cats if taxonomy.suitability(c, prop.type, prop.size_sqft)[0] > 0]
        if fitting:
            return fitting[0]
    elif cats:
        return cats[0]
    q = select(Demand.category, func.sum(Demand.verified_support_count).label("s")).where(Demand.status.in_(LIVE))
    q = q.where(within("demands", prop.lat, prop.lng, PROPERTY_CATCHMENT_M)) if prop else q.where(Demand.area_id == area.id)
    for slug, _ in db.execute(q.group_by(Demand.category).order_by(func.sum(Demand.verified_support_count).desc())).all():
        if not prop or taxonomy.suitability(slug, prop.type, prop.size_sqft)[0] > 0:
            return slug
    return cats[0] if cats else "other"


def _scope_demands(db: Session, category: str, area: OpportunityArea, prop: Property | None) -> list[Demand]:
    q = select(Demand).where(Demand.status.in_(LIVE), Demand.category == category)
    q = q.where(within("demands", prop.lat, prop.lng, PROPERTY_CATCHMENT_M)) if prop else q.where(Demand.area_id == area.id)
    return list(db.scalars(q.order_by(Demand.verified_support_count.desc())))


def _competitors(area: OpportunityArea, category: str) -> int:
    return int(((area.stats or {}).get("competition") or {}).get(category, 0))


def _footfall(area: OpportunityArea) -> float:
    return float(((area.stats or {}).get("access") or {}).get("footfall_index", 0.5))


def _area_supporters(db: Session, city: str, category: str) -> dict[uuid.UUID, tuple[int, int]]:
    rows = db.execute(select(Demand.area_id, func.coalesce(func.sum(Demand.verified_support_count), 0), func.count(Demand.id))
                      .join(OpportunityArea, OpportunityArea.id == Demand.area_id)
                      .where(Demand.status.in_(LIVE), Demand.category == category, OpportunityArea.city == city)
                      .group_by(Demand.area_id)).all()
    return {aid: (int(s), int(n)) for aid, s, n in rows}


# ---------------------------------------------------------------- competitor gap
def _gap_score(supporters: int, competitors: int, per_outlet: float, city_avg: float) -> int:
    strength = taxonomy.demand_strength(supporters, 150)
    relief = 1 / (1 + competitors / 2)
    relative = min(1.0, (per_outlet / city_avg) / 3) if city_avg > 0 else (1.0 if supporters else 0.0)
    score = round(100 * (0.45 * strength + 0.35 * relief + 0.20 * relative))
    return min(score, 25) if supporters == 0 else score


def _gap_label(score: int, supporters: int) -> tuple[str, str]:
    if supporters == 0:
        return "No proven demand yet", "early"
    if score >= 70:
        return "Wide gap", "strong"
    if score >= 50:
        return "Clear gap", "promising"
    if score >= 30:
        return "Narrow gap", "early"
    return "Crowded", "warn"


def _intensity(competitors: int) -> str:
    return "None recorded" if competitors == 0 else "Light" if competitors <= 2 else "Moderate" if competitors <= 5 else "Heavy"


def _plural(cat: taxonomy.Category, n: int) -> str:
    name = cat.name.lower()
    if n == 1 or name.endswith("s"):
        return name
    if name.endswith("y") and name[-2:-1] not in "aeiou":
        return name[:-1] + "ies"  # pharmacy -> pharmacies
    return name + "s"


def competitor_gap(db: Session, category: str, area: OpportunityArea, prop: Property | None) -> dict:
    cat = taxonomy.get(category)
    demands = _scope_demands(db, cat.slug, area, prop)
    supporters = sum(d.verified_support_count for d in demands)
    competitors = _competitors(area, cat.slug)
    footfall = _footfall(area)
    per_outlet = supporters / max(competitors, 1)

    city_areas = list(db.scalars(select(OpportunityArea).where(OpportunityArea.city == area.city)))
    by_area = _area_supporters(db, area.city, cat.slug)
    city_supporters = sum(s for s, _ in by_area.values())
    city_outlets = sum(_competitors(a, cat.slug) for a in city_areas)
    city_avg = city_supporters / city_outlets if city_outlets else 0.0
    score = _gap_score(supporters, competitors, per_outlet, city_avg)
    label, tone = _gap_label(score, supporters)

    neighbours = []
    for a in city_areas:
        dist = haversine_m(area.lat, area.lng, a.lat, a.lng)
        if dist > NEIGHBOUR_RADIUS_M and a.id != area.id:
            continue
        s, _ = by_area.get(a.id, (0, 0))
        c = _competitors(a, cat.slug)
        po = s / max(c, 1)
        sc = _gap_score(s, c, po, city_avg)
        lab, tn = _gap_label(sc, s)
        neighbours.append({"area": {"id": str(a.id), "name": a.name}, "distance_km": round(dist / 1000, 1),
                           "supporters": s, "competitors": c, "per_outlet": round(po, 1), "score": sc,
                           "label": lab, "tone": tn, "current": a.id == area.id})
    neighbours.sort(key=lambda r: (r["score"], r["supporters"]), reverse=True)
    current_rank = next((i + 1 for i, r in enumerate(neighbours) if r["current"]), None)

    weight = {d.id: max(d.verified_support_count, 1) for d in demands}
    total_w = sum(weight.values()) or 1
    gaps: dict[str, int] = {}
    for d in demands:
        text = " ".join(filter(None, [d.title, d.description, d.reason_note, " ".join(d.tags or [])]))
        for gap_label, rx in SERVICE_GAPS:
            if rx.search(text):
                gaps[gap_label] = gaps.get(gap_label, 0) + weight[d.id]
    service_gaps = [{"label": k, "supporters": v, "share": round(v / total_w, 3)}
                    for k, v in sorted(gaps.items(), key=lambda kv: kv[1], reverse=True)]
    audience: dict[str, int] = {}
    for d in demands:
        audience[d.reason] = audience.get(d.reason, 0) + weight[d.id]
    audience_out = [{"reason": k, "label": taxonomy.REASONS.get(k, "Other"), "supporters": v, "share": round(v / total_w, 3)}
                    for k, v in sorted(audience.items(), key=lambda kv: kv[1], reverse=True)] if demands else []

    complements = []
    for slug in COMPLEMENTS.get(cat.slug, []):
        n = _competitors(area, slug)
        if n:
            other = taxonomy.get(slug)
            complements.append({"category": slug, "name": other.name, "count": n,
                                "text": f"{n} {_plural(other, n)} nearby already draw people who also need {cat.noun}"})

    reasons = []
    if supporters:
        reasons.append(f"{supporters:,} verified residents want {cat.noun} {'within 2 km of this space' if prop else 'in ' + area.name}")
    else:
        reasons.append(f"No verified requests for {cat.noun} {'near this space' if prop else 'in ' + area.name} yet")
    if competitors == 0:
        reasons.append(f"No existing {cat.name.lower()} recorded in {area.name}")
    else:
        reasons.append(f"{competitors} existing {_plural(cat, competitors)} in {area.name}: {_intensity(competitors).lower()} competition")
    if supporters and city_avg:
        ratio = per_outlet / city_avg
        reasons.append(f"{per_outlet:,.0f} supporters per outlet here, {ratio:.1f}× the {area.city} average of {city_avg:,.0f}"
                       if competitors else f"Every supporter here is unserved locally (the {area.city} average is {city_avg:,.0f} per outlet)")
    if service_gaps:
        reasons.append(f"Residents specifically ask for: {service_gaps[0]['label'].lower()}")
    reasons.append(f"Footfall index {footfall * 100:.0f}/100, "
                   f"{'above' if footfall >= 0.7 else 'around' if footfall >= 0.55 else 'below'} the typical local market")
    better = [n for n in neighbours if not n["current"] and n["score"] > score]
    if better:
        reasons.append(f"{better[0]['area']['name']} ({better[0]['distance_km']} km away) shows an even wider gap")
    elif len(neighbours) > 1 and supporters:
        reasons.append("This is the widest gap within 5 km")

    summary = {
        "Wide gap": f"Strong verified demand for {cat.noun} and "
                    + (f"no existing {_plural(cat, 2)} serving it." if competitors == 0
                       else f"only {competitors} existing {_plural(cat, competitors)} serving it."),
        "Clear gap": f"Real demand for {cat.noun} that existing outlets don't fully cover.",
        "Narrow gap": f"Some demand for {cat.noun}, but existing outlets already cover much of it.",
        "Crowded": f"Plenty of {_plural(cat, 2)} already serve the demand here.",
        "No proven demand yet": f"No residents have asked for {cat.noun} here yet, so the gap is unproven.",
    }[label]
    return {
        "category": cat.slug, "category_name": cat.name, "scope": "property" if prop else "area",
        "area": {"id": str(area.id), "name": area.name, "city": area.city},
        "property_id": str(prop.id) if prop else None,
        "verdict": {"label": label, "tone": tone, "score": score, "summary": summary},
        "metrics": {"supporters": supporters, "requests": len(demands), "competitors": competitors,
                    "intensity": _intensity(competitors), "per_outlet": round(per_outlet, 1),
                    "city_avg_per_outlet": round(city_avg, 1), "footfall_index": footfall,
                    "rank_nearby": current_rank, "areas_nearby": len(neighbours)},
        "service_gaps": service_gaps[:5], "audience": audience_out, "complements": complements,
        "neighbours": neighbours[:7], "reasons": reasons,
        "top_requests": [{"id": str(d.id), "title": d.title, "locality": d.locality, "supporters": d.verified_support_count}
                         for d in demands[:3]],
        "sources": "Demand: verified BizYukti requests. Competitors and footfall: area survey data (illustrative in this demo build).",
    }


# ---------------------------------------------------------------- financial feasibility
def _median(values: list[float], fallback: float) -> float:
    vals = [v for v in values if v and v > 0]
    return float(statistics.median(vals)) if vals else fallback


def _typical_space(db: Session, cat: taxonomy.Category, area: OpportunityArea) -> dict:
    lo, hi = taxonomy.size_window(cat.slug)
    rows = db.execute(select(Property.size_sqft, Property.price_amount, Property.type).where(
        Property.status == "published", Property.area_id == area.id, Property.price_type == "rent",
        Property.size_sqft > 0, Property.price_amount > 0)).all()
    fitting = [r for r in rows if r.type in cat.types and lo <= r.size_sqft <= hi]
    city_rates = db.scalars(select(Property.price_amount / Property.size_sqft).join(
        OpportunityArea, OpportunityArea.id == Property.area_id).where(
        Property.status == "published", Property.price_type == "rent", OpportunityArea.city == area.city,
        Property.size_sqft > 0, Property.price_amount > 0)).all()
    rate = _median([r.price_amount / r.size_sqft for r in (fitting or rows)], _median(list(city_rates), 30.0))
    size = _median([r.size_sqft for r in fitting], round(math.sqrt(cat.size[0] * cat.size[1]) / 50) * 50)
    return {"size_sqft": round(size), "rent": round(size * rate / 100) * 100, "rate": round(rate, 1),
            "based_on": len(fitting or rows)}


def _emi(principal: float) -> float:
    r, n = LOAN_RATE / 12, LOAN_YEARS * 12
    return principal * r * (1 + r) ** n / ((1 + r) ** n - 1)


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


ASSUMPTION_LIMITS = {"ticket": (1, 1_000_000), "margin_pct": (1, 99), "reach": (1, 50), "staff": (0, 200),
                     "salary": (0, 500_000), "rent": (0, 50_000_000), "fitout": (0, 50_000), "inventory": (0, 500_000_000)}


def feasibility(db: Session, category: str, area: OpportunityArea, prop: Property | None,
                profile: BusinessProfile | None, overrides: dict | None = None) -> dict:
    cat = taxonomy.get(category)
    base = BENCHMARKS.get(cat.slug, BENCHMARKS["other"])
    ov = {k: _clamp(float(v), *ASSUMPTION_LIMITS[k]) for k, v in (overrides or {}).items()
          if k in ASSUMPTION_LIMITS and v is not None}
    bm = replace(base, ticket=round(ov.get("ticket", base.ticket)), margin=ov.get("margin_pct", base.margin * 100) / 100,
                 staff=round(ov.get("staff", base.staff)), salary=round(ov.get("salary", base.salary)),
                 fitout=round(ov.get("fitout", base.fitout)), inventory=round(ov.get("inventory", base.inventory)))
    reach = ov.get("reach", REACH)

    # The space being evaluated: a real listing, or a typical space for this business in the area.
    if prop:
        size = prop.size_sqft or _typical_space(db, cat, area)["size_sqft"]
        space = {"source": "listing", "property_id": str(prop.id), "type": prop.type,
                 "title": f"{taxonomy.PROPERTY_TYPES.get(prop.type, 'space').capitalize()}, {size:,.0f} sq ft",
                 "locality": prop.locality or area.name, "size_sqft": size, "price_type": prop.price_type,
                 "price_amount": prop.price_amount, "negotiable": prop.price_negotiable}
        price_type, price = prop.price_type, prop.price_amount
    else:
        t = _typical_space(db, cat, area)
        size = t["size_sqft"]
        space = {"source": "typical", "property_id": None, "type": cat.types[0],
                 "title": f"Typical {size:,.0f} sq ft space for {cat.noun}", "locality": area.name, "size_sqft": size,
                 "price_type": "rent", "price_amount": t["rent"], "negotiable": False,
                 "note": f"Rent estimated at ₹{t['rate']:,.0f}/sq ft from {t['based_on']} listing{'s' if t['based_on'] != 1 else ''} nearby"}
        price_type, price = "rent", t["rent"]
    if price_type == "sale" and price:
        down_payment, occupancy = price * (1 - LOAN_SHARE), _emi(price * LOAN_SHARE)
        occupancy_label = "Loan EMI"
    else:
        down_payment, occupancy = 0.0, float(price or _typical_space(db, cat, area)["rent"])
        occupancy_label = "Rent"
    if "rent" in ov:
        occupancy = ov["rent"]

    # Demand side.
    demands = _scope_demands(db, cat.slug, area, prop)
    supporters = sum(d.verified_support_count for d in demands)
    competitors = _competitors(area, cat.slug)
    footfall = _footfall(area)
    # People who asked split their custom between you and existing outlets; passing footfall splits more gently.
    share = 0.75 / (1 + 0.6 * competitors)
    walk_share = 0.9 / (1 + 0.25 * competitors)
    potential = supporters * reach
    raw_units = potential * bm.per_supporter * share + footfall * bm.walkins * walk_share
    capacity = bm.fixed_capacity or (size / bm.capacity_sqft if bm.capacity_sqft else None)

    staff_cost = bm.staff * bm.salary
    utilities = bm.utilities * size
    fixed = occupancy + staff_cost + utilities + bm.other

    def month(units: float) -> dict:
        units = min(units, capacity) if capacity else units
        revenue = round(units * bm.ticket)
        costs = {"cogs": round(revenue * (1 - bm.margin)), "occupancy": round(occupancy), "staff": round(staff_cost),
                 "utilities": round(utilities), "other": round(bm.other)}
        profit = revenue - sum(costs.values())  # from the rounded lines, so the P&L always adds up
        return {"units": round(units, 1), "revenue": revenue, "profit": profit, "costs": costs,
                "margin_pct": round(profit / revenue * 100, 1) if revenue else None}

    scenarios = [{"key": k, "label": lab, "factor": f, **month(raw_units * f)} for k, lab, f in SCENARIOS]
    exp = scenarios[1]
    capped = bool(capacity and raw_units > capacity)

    setup_items = {"fitout": round(bm.fitout * size), "deposit": round(occupancy * DEPOSIT_MONTHS) if price_type != "sale" else 0,
                   "down_payment": round(down_payment), "stock": bm.inventory, "licences": LICENCES}
    setup = sum(setup_items.values())

    # Cash curve with a launch ramp; payback is the first month cumulative cash turns positive.
    # The chart shows the first HORIZON months; payback is searched up to PAYBACK_LIMIT months.
    cumulative, curve, payback = -setup, [], None
    for m in range(1, PAYBACK_LIMIT + 1):
        factor = RAMP[m - 1] if m <= len(RAMP) else 1.0
        cumulative += month(raw_units * factor)["profit"]
        if m <= HORIZON:
            curve.append({"month": m, "cash": round(cumulative)})
        if payback is None and cumulative >= 0:
            payback = m
        if m >= HORIZON and payback is not None:
            break

    breakeven_revenue = fixed / bm.margin if bm.margin > 0 else None
    breakeven_units = breakeven_revenue / bm.ticket if breakeven_revenue else None
    per_day = bm.model == "retail"
    cushion = exp["units"] / breakeven_units if breakeven_units else 0
    rent_ratio = occupancy / exp["revenue"] if exp["revenue"] else None
    unit_word = "customers a day" if per_day else "paying members"
    fmt_units = (lambda u: f"{u / 30:,.0f} {unit_word}") if per_day else (lambda u: f"{u:,.0f} {unit_word}")

    checks = []
    checks.append({"key": "profit", "label": "Monthly profit", "status": "good" if exp["profit"] > 0 else "bad",
                   "detail": f"₹{exp['profit']:,.0f} a month once sales settle" if exp["profit"] > 0
                   else f"Loses ₹{-exp['profit']:,.0f} a month even at expected demand"})
    if breakeven_units:
        checks.append({"key": "cushion", "label": "Break-even cushion",
                       "status": "good" if cushion >= 1.3 else "warn" if cushion >= 1.0 else "bad",
                       "detail": f"Needs {fmt_units(breakeven_units)} to break even; local demand supports about {fmt_units(exp['units'])}"})
    if rent_ratio is not None:
        checks.append({"key": "rent", "label": f"{occupancy_label} to revenue",
                       "status": "good" if rent_ratio <= 0.12 else "warn" if rent_ratio <= 0.2 else "bad",
                       "detail": f"{rent_ratio * 100:.0f}% of expected revenue (healthy is under 12%)"})
    checks.append({"key": "payback", "label": "Payback",
                   "status": "good" if payback and payback <= 24 else "warn" if payback and payback <= 48 else "bad",
                   "detail": f"Setup cost of ₹{setup:,.0f} earned back in month {payback}" if payback
                   else f"Setup cost of ₹{setup:,.0f} isn't earned back within {PAYBACK_LIMIT // 12} years"})
    low = scenarios[0]
    checks.append({"key": "downside", "label": "If demand is 30% lower", "status": "good" if low["profit"] >= 0 else "warn",
                   "detail": f"Still makes ₹{low['profit']:,.0f} a month" if low["profit"] >= 0 else f"Loses ₹{-low['profit']:,.0f} a month"})
    if profile and profile.budget_max and price_type != "sale":
        checks.append({"key": "budget", "label": "Within your budget", "status": "good" if occupancy <= profile.budget_max else "warn",
                       "detail": f"Rent ₹{occupancy:,.0f} vs your budget of ₹{profile.budget_max:,.0f}"})
    type_fit, size_fit = taxonomy.suitability(cat.slug, space["type"], size)
    lo, hi = cat.size
    checks.append({"key": "size", "label": "Space fit", "status": "good" if type_fit and size_fit >= 0.9 else "warn" if type_fit else "bad",
                   "detail": f"{size:,.0f} sq ft vs a typical {cat.name.lower()} of {lo:,}–{hi:,} sq ft"
                   + ("" if type_fit else f"; a {taxonomy.PROPERTY_TYPES.get(space['type'], 'space')} rarely suits {cat.noun}")})

    s1 = _clamp((cushion - 0.8) / 0.8, 0, 1)
    s2 = _clamp((48 - payback) / 36, 0, 1) if payback else 0.0
    s3 = _clamp((0.30 - rent_ratio) / 0.22, 0, 1) if rent_ratio is not None else 0.0
    s4 = 1.0 if low["profit"] >= 0 else 0.0
    score = round(100 * (0.35 * s1 + 0.30 * s2 + 0.20 * s3 + 0.15 * s4))
    if exp["profit"] <= 0 or (rent_ratio is not None and rent_ratio > 0.25) or not type_fit or payback is None:
        status, tone = "Not feasible", "bad"
        summary = (f"At expected demand this {cat.name.lower()} would lose money each month." if exp["profit"] <= 0
                   else f"This kind of space doesn't suit {cat.noun}." if not type_fit
                   else f"{occupancy_label} would take {rent_ratio * 100:.0f}% of revenue, too much to stay healthy."
                   if rent_ratio is not None and rent_ratio > 0.25
                   else f"Profit is too thin to earn back the ₹{setup:,.0f} setup cost within {PAYBACK_LIMIT // 12} years.")
    elif payback and payback <= 24 and low["profit"] >= 0 and rent_ratio is not None and rent_ratio <= 0.15:
        status, tone = "Feasible", "good"
        summary = f"Profitable at expected demand, pays back setup in about {payback} months, and holds up if demand is lower."
    else:
        status, tone = "Marginal", "warn"
        weak = [c["label"].lower() for c in checks if c["status"] != "good"]
        summary = "Can work, but watch " + (", ".join(weak[:2]) if weak else "the assumptions") + "."

    unit_label = "Customers a day" if per_day else "Paying members"
    assumptions = [
        {"key": "ticket", "label": "Average bill" if per_day else "Monthly fee per member", "value": bm.ticket, "base": base.ticket, "unit": "₹"},
        {"key": "margin_pct", "label": "Gross margin", "value": round(bm.margin * 100, 1), "base": round(base.margin * 100, 1), "unit": "%"},
        {"key": "reach", "label": "Customers per verified supporter", "value": reach, "base": REACH, "unit": "×"},
        {"key": "rent", "label": f"Monthly {occupancy_label.lower()}", "value": round(occupancy),
         "base": round(_emi(price * LOAN_SHARE)) if price_type == "sale" and price else round(price or 0), "unit": "₹"},
        {"key": "staff", "label": "Staff", "value": bm.staff, "base": base.staff, "unit": "people"},
        {"key": "salary", "label": "Salary per person", "value": bm.salary, "base": base.salary, "unit": "₹/month"},
        {"key": "fitout", "label": "Fit-out per sq ft", "value": bm.fitout, "base": base.fitout, "unit": "₹"},
        {"key": "inventory", "label": "Opening stock and equipment", "value": bm.inventory, "base": base.inventory, "unit": "₹"},
    ]
    return {
        "category": cat.slug, "category_name": cat.name, "model": bm.model, "unit_label": unit_label, "per_day": per_day,
        "area": {"id": str(area.id), "name": area.name, "city": area.city},
        "space": space, "occupancy_label": occupancy_label,
        "status": {"label": status, "tone": tone, "score": score, "summary": summary},
        "demand": {"supporters": supporters, "reach": reach, "potential_customers": round(potential), "competitors": competitors,
                   "share_pct": round(share * 100, 1), "walkin_share_pct": round(walk_share * 100, 1), "footfall_index": footfall,
                   "capacity": round(capacity) if capacity else None, "capped": capped},
        "expected": exp, "scenarios": scenarios,
        "breakeven": {"revenue": round(breakeven_revenue) if breakeven_revenue else None,
                      "units": round(breakeven_units, 1) if breakeven_units else None,
                      "per_day": round(breakeven_units / 30, 1) if breakeven_units and per_day else None,
                      "cushion": round(cushion, 2)},
        "rent_ratio": round(rent_ratio, 3) if rent_ratio is not None else None,
        "setup": {"total": setup, "items": setup_items}, "payback_month": payback, "cash_curve": curve,
        "checks": checks, "assumptions": assumptions, "customised": bool(ov),
        "notes": [n for n in [
            f"Demand: {supporters:,} verified supporters × {reach:g} customers each, {share * 100:.0f}% captured against "
            f"{competitors} competitor{'s' if competitors != 1 else ''}, plus {walk_share * 100:.0f}% of passing footfall "
            f"(index {footfall * 100:.0f}/100).",
            f"Launch ramp: {RAMP[0] * 100:.0f}% of steady sales in month 1, rising to full by month {len(RAMP) + 1}.",
            f"Setup includes {DEPOSIT_MONTHS} months' deposit, fit-out, opening stock and ₹{LICENCES:,} for licences and launch."
            if price_type != "sale" else f"Purchase modelled as {100 - LOAN_SHARE * 100:.0f}% down payment and a {LOAN_YEARS}-year loan at {LOAN_RATE * 100:.1f}%.",
            "Capacity limits what this space can serve." if capped else None,
            "Planning estimate from typical costs for this business in a tier-2 Indian city. Not financial advice.",
        ] if n],
    }

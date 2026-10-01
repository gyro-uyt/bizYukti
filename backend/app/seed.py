"""Demo data for a Gwalior pilot.

Everything here is synthetic and illustrative: area centres are approximate, and every person,
business, listing, count and note is invented for demonstration. Refuses to run in production.

    python -m app.seed --reset      # wipe and reseed
    python -m app.seed --if-empty   # seed only a fresh database (used by docker compose)
"""

import argparse
import io
import math
import random
import shutil
import sys
from datetime import timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps
from sqlalchemy import func, select, text

from .config import settings
from .db import Base, SessionLocal
from .geo import haversine_m
from .models import (BusinessProfile, Demand, DemandInterest, DemandSupport, Inquiry, Match, Message,
                     OpportunityArea, Property, RewardLedger, SavedItem, User, UserRole, Verification)
from .security import keyed_hash, utcnow
from .services import demands as demand_svc
from .services import matching, media, rewards, trust
from .storage import get_storage

R = random.Random(20261001)
CITY = "Gwalior"

# slug: (name, lat, lng, radius_m, footfall, transit, road, notes, competition)
AREAS = {
    "gol-pahadiya": ("Gol Pahadiya", 26.2330, 78.1590, 1500, 0.78, "high", "Busy main road with shopfronts",
                     "Dense residential lanes with schools within walking distance",
                     {"pharmacy": 1, "grocery": 6, "cafe": 1, "bookstore": 0, "clinic": 2, "bakery": 2}),
    "lashkar": ("Lashkar", 26.2010, 78.1510, 1800, 0.85, "high", "Old-city market streets",
                "Heavy daytime footfall from the markets", {"pharmacy": 7, "grocery": 12, "bookstore": 2, "clinic": 5}),
    "maharaj-bada": ("Maharaj Bada", 26.1975, 78.1585, 1200, 0.92, "high", "Central square, limited parking",
                     "Shopping footfall all day", {"pharmacy": 5, "restaurant": 3, "salon": 4, "cafe": 3}),
    "phool-bagh": ("Phool Bagh", 26.2110, 78.1680, 1400, 0.66, "medium", "Wide arterial road",
                   "Parks and offices with evening walkers", {"gym": 1, "pharmacy": 2, "pet_care": 0, "cafe": 2}),
    "city-centre": ("City Centre", 26.2075, 78.1960, 1600, 0.88, "high", "Commercial roads with offices",
                    "Office workers and students on weekdays", {"cafe": 6, "coworking": 1, "pharmacy": 4, "gym": 3}),
    "thatipur": ("Thatipur", 26.2185, 78.2110, 1500, 0.71, "medium", "Mixed residential and market road",
                 "Family neighbourhoods; markets busy after 6 pm", {"grocery": 2, "gym": 0, "pharmacy": 3, "bank_atm": 1}),
    "morar": ("Morar", 26.2280, 78.2270, 1800, 0.74, "medium", "Main market road",
              "Large residential catchment", {"clinic": 1, "diagnostics": 0, "pharmacy": 4, "grocery": 5}),
    "hazira": ("Hazira", 26.2430, 78.1765, 1500, 0.69, "medium", "Industrial and residential mix",
               "Shift workers keep demand up late in the evening", {"pharmacy": 1, "bakery": 1, "coaching": 2, "grocery": 4}),
    "kampoo": ("Kampoo", 26.1905, 78.1660, 1300, 0.63, "medium", "Hospital road",
               "Hospital visitors and staff", {"pharmacy": 3, "hardware": 1, "clinic": 3}),
    "dd-nagar": ("DD Nagar", 26.2585, 78.2005, 1700, 0.58, "low", "Planned colony roads",
                 "Newer colonies with young families", {"grocery": 1, "daycare": 0, "pharmacy": 1, "gym": 1}),
    "vinay-nagar": ("Vinay Nagar", 26.2500, 78.2130, 1500, 0.61, "medium", "Colony roads near the bypass",
                    "Students renting rooms in nearby colonies", {"coaching": 1, "pharmacy": 1, "cafe": 0}),
    "padav": ("Padav", 26.2195, 78.1835, 1200, 0.81, "high", "Busy through-road",
              "Commuter traffic through the day", {"bank_atm": 2, "laundry": 0, "pharmacy": 3, "restaurant": 4}),
    "tansen-nagar": ("Tansen Nagar", 26.2285, 78.1705, 1300, 0.64, "medium", "Residential main road",
                     "Quiet residential lanes", {"grocery": 2, "electronics": 1, "bakery": 0, "pharmacy": 2}),
    "gandhi-nagar": ("Gandhi Nagar", 26.2010, 78.2065, 1400, 0.67, "medium", "Wide roads with open plots",
                     "Colleges nearby and evening sports demand", {"sports": 0, "bakery": 1, "cafe": 2}),
}
HOME_WEIGHTS = {"gol-pahadiya": 3, "tansen-nagar": 2, "hazira": 2, "padav": 2, "phool-bagh": 2}

# (area, category, title, supporters, reason, days since published, share of support in the last 14 days, author)
DEMANDS = [
    ("gol-pahadiya", "pharmacy", "Pharmacy", 184, "daily_need", 62, 0.45, None),
    ("gol-pahadiya", "bookstore", "Bookstore near the park", 46, "students", 40, 0.3, "asha"),
    ("gol-pahadiya", "cafe", "Café with seating", 28, "other", 30, 0.5, None),
    ("thatipur", "grocery", "Grocery store open late", 142, "daily_need", 55, 0.35, None),
    ("thatipur", "gym", "Gym for women", 61, "family", 45, 0.4, None),
    ("morar", "clinic", "Children's clinic", 118, "family", 58, 0.3, None),
    ("morar", "diagnostics", "Diagnostic lab", 37, "daily_need", 33, 0.3, None),
    ("hazira", "pharmacy", "24-hour pharmacy", 74, "daily_need", 41, 0.5, None),
    ("hazira", "bakery", "Bakery", 22, "family", 20, 0.4, None),
    ("city-centre", "coworking", "Co-working space", 88, "commute", 50, 0.45, None),
    ("city-centre", "cafe", "Quiet café to work from", 57, "commute", 36, 0.35, None),
    ("dd-nagar", "grocery", "Supermarket", 96, "daily_need", 52, 0.3, None),
    ("dd-nagar", "daycare", "Daycare for working parents", 51, "family", 44, 0.35, None),
    ("vinay-nagar", "coaching", "Coaching centre for competitive exams", 69, "students", 48, 0.4, None),
    ("vinay-nagar", "pharmacy", "Pharmacy", 33, "daily_need", 26, 0.4, None),
    ("padav", "bank_atm", "ATM", 44, "commute", 29, 0.3, None),
    ("padav", "laundry", "Laundry and ironing", 19, "daily_need", 18, 0.5, None),
    ("lashkar", "bookstore", "Bookstore", 26, "students", 34, 0.2, None),
    ("lashkar", "clinic", "Dental clinic", 31, "family", 31, 0.3, None),
    ("maharaj-bada", "restaurant", "Family restaurant", 64, "family", 47, 0.3, None),
    ("maharaj-bada", "salon", "Unisex salon", 17, "other", 16, 0.4, None),
    ("phool-bagh", "gym", "Gym", 42, "daily_need", 39, 0.35, None),
    ("phool-bagh", "pet_care", "Pet clinic", 14, "other", 15, 0.4, None),
    ("kampoo", "pharmacy", "Medical store", 58, "daily_need", 43, 0.3, None),
    ("kampoo", "hardware", "Hardware store", 12, "daily_need", 14, 0.3, None),
    ("tansen-nagar", "grocery", "Vegetable and fruit shop", 39, "daily_need", 27, 0.4, None),
    ("tansen-nagar", "electronics", "Phone repair shop", 11, "other", 12, 0.5, None),
    ("tansen-nagar", "bakery", "Bakery", 24, "family", 70, 0.1, "asha:fulfilled"),
    ("gandhi-nagar", "sports", "Box cricket turf", 47, "students", 37, 0.45, None),
    ("gandhi-nagar", "bakery", "Bakery", 9, "family", 9, 0.5, None),
    ("morar", "delivery_hub", "Quick delivery store", 8, "daily_need", 8, 0.6, None),
    ("thatipur", "bank_atm", "ATM", 6, "commute", 6, 0.5, None),
    ("hazira", "coaching", "Spoken English classes", 3, "students", 3, 0.6, None),
]

# (area, north_m, east_m, type, size, unit, price_type, amount, negotiable, available_in_days, description, amenities, owner, verified)
PROPERTIES = [
    ("gol-pahadiya", 180, -120, "shop", 850, "sqft", "rent", 28000, False, 0,
     "Ground-floor shop on the main road with a wide shutter and a small storage room at the back.",
     ["ground_floor", "road_facing", "storage", "washroom"], "rajesh", True),
    ("gol-pahadiya", -350, 260, "shop", 420, "sqft", "rent", 18000, False, 0,
     "Corner shop facing the school road. Good for daily-need retail.", ["ground_floor", "road_facing"], 1, False),
    ("gol-pahadiya", 520, 400, "shop", 260, "sqft", "rent", 12000, False, 0,
     "Compact shop in a busy lane, freshly painted, shutter replaced last year.", ["ground_floor"], 2, False),
    ("gol-pahadiya", -600, -500, "shop", 640, "sqft", "rent", 24000, False, 20,
     "Shop in a new complex with parking for two-wheelers, ready next month.", ["ground_floor", "parking", "power_backup"], 3, False),
    ("gol-pahadiya", 900, -200, "shop", 1100, "sqft", "rent", 38000, True, 0,
     "Large showroom-style shop with a glass front and 3-phase power.", ["road_facing", "parking", "three_phase"], 4, True),
    ("gol-pahadiya", -150, 820, "shop", 190, "sqft", "rent", 9000, False, 0,
     "Small shop near the bus stop with steady walk-in traffic.", ["road_facing"], 5, False),
    ("gol-pahadiya", 300, 950, "shop", 55, "sqm", "rent", 21000, False, 0,
     "First-floor shop with stairs from the main road and a washroom.", ["washroom"], 6, False),
    ("hazira", 100, 150, "shop", 300, "sqft", "rent", 13000, False, 0,
     "Shop on the main road, open frontage, near two bus stops.", ["ground_floor", "road_facing"], 7, False),
    ("hazira", -400, 300, "warehouse", 4200, "sqft", "rent", 65000, False, 0,
     "Warehouse with a loading bay, 3-phase power and a water connection.", ["three_phase", "parking", "water"], 8, False),
    ("thatipur", 150, -100, "shop", 1200, "sqft", "rent", 42000, False, 0,
     "Double-shutter shop in the market road, suits a supermarket or grocery.", ["ground_floor", "road_facing", "storage"], 9, True),
    ("thatipur", -300, 200, "shop", 750, "sqft", "rent", 26000, False, 35,
     "Ground-floor shop in a residential block, available after current tenant leaves.", ["ground_floor"], 10, False),
    ("morar", 200, 300, "shop", 600, "sqft", "rent", 22000, False, 0,
     "Clean ground-floor space, previously a clinic, with a waiting area.", ["ground_floor", "washroom", "water"], 11, False),
    ("morar", -250, -150, "office", 900, "sqft", "rent", 27000, False, 0,
     "First-floor office with three cabins. Suits a clinic or a lab.", ["washroom", "power_backup"], 12, False),
    ("city-centre", 120, -80, "office", 1400, "sqft", "rent", 45000, False, 0,
     "Open-plan office on the second floor with lift access and power backup.",
     ["power_backup", "washroom", "parking"], "rajesh", False),
    ("city-centre", -200, 250, "office", 2600, "sqft", "rent", 85000, True, 0,
     "Full floor office with meeting rooms. Ideal for a co-working operator.", ["power_backup", "parking", "washroom"], 13, True),
    ("city-centre", 300, 100, "shop", 480, "sqft", "rent", 35000, False, 0,
     "Shop with seating space in front, near offices and a college.", ["ground_floor", "road_facing"], 14, False),
    ("dd-nagar", 100, 100, "warehouse", 2600, "sqft", "rent", 48000, False, 0,
     "Hall-type space with high ceiling and wide entrance. Suits a supermarket.", ["ground_floor", "parking", "three_phase"], 15, False),
    ("dd-nagar", -200, 250, "shop", 900, "sqft", "rent", 20000, False, 0,
     "Ground-floor space with a small courtyard, quiet colony road.", ["ground_floor", "water", "washroom"], 16, False),
    ("vinay-nagar", 150, -200, "office", 1100, "sqft", "rent", 25000, False, 0,
     "Office with two halls, suits classrooms. Students' area nearby.", ["power_backup", "washroom"], 17, False),
    ("vinay-nagar", -100, 120, "shop", 350, "sqft", "rent", 14000, False, 0,
     "Ground-floor shop on the colony main road.", ["ground_floor", "road_facing"], 18, False),
    ("padav", 50, 60, "shop", 120, "sqft", "rent", 15000, False, 0,
     "Small shop right on the through-road. Suits an ATM or a kiosk.", ["road_facing", "power_backup"], 19, False),
    ("padav", -150, -90, "shop", 280, "sqft", "rent", 16000, False, 10,
     "Shop with water connection at the back, suits laundry.", ["water", "ground_floor"], 20, False),
    ("lashkar", 100, -50, "shop", 380, "sqft", "rent", 20000, False, 0,
     "Shop in the old market with steady footfall.", ["ground_floor"], 1, False),
    ("maharaj-bada", 80, 120, "shop", 1600, "sqft", "rent", 70000, True, 0,
     "Two-level shop near the square. Suits a restaurant.", ["road_facing", "washroom", "water"], 2, False),
    ("phool-bagh", -120, 160, "shop", 2200, "sqft", "rent", 52000, False, 0,
     "Basement plus ground floor hall, suits a gym.", ["power_backup", "washroom", "parking"], 3, False),
    ("kampoo", 90, -60, "shop", 320, "sqft", "rent", 17000, False, 0,
     "Shop facing the hospital road.", ["ground_floor", "road_facing"], 4, False),
    ("tansen-nagar", 60, 140, "shop", 450, "sqft", "rent", 15000, False, 0,
     "Shop with a front verandah in a residential lane.", ["ground_floor"], 5, False),
    ("gandhi-nagar", 300, -400, "land", 12000, "sqft", "sale", 13_500_000, True, 0,
     "Open plot with road access. Suits a sports turf or a delivery hub.", ["road_facing", "water"], 6, False),
    ("gandhi-nagar", -150, 100, "shop", 400, "sqft", "rent", 19000, False, 0,
     "Shop near the colleges with evening footfall.", ["ground_floor", "road_facing"], 7, False),
]

BUSINESSES = [  # (name, categories, budget_max, size_min, size_max, verification)
    ("CareWell Pharmacy", ["pharmacy"], 40000, 200, 900, "verified"),
    ("Jeevan Medicos", ["pharmacy"], 30000, 150, 700, "verified"),
    ("Sanjeevani Chemists", ["pharmacy"], 35000, 150, 800, "unverified"),
    ("HealthFirst Pharmacy", ["pharmacy", "diagnostics"], 50000, 200, 1200, "verified"),
    ("Apna Kirana Mart", ["grocery"], 60000, 400, 3000, "verified"),
    ("Brewline Café", ["cafe"], 45000, 300, 1200, "pending"),
    ("IronCore Fitness", ["gym"], 70000, 1500, 5000, "unverified"),
    ("Little Steps Daycare", ["daycare"], 30000, 800, 2500, "unverified"),
    ("Pragati Classes", ["coaching"], 35000, 600, 2000, "verified"),
    ("Glow Unisex Salon", ["salon"], 30000, 250, 1000, "unverified"),
    ("Workbay Co-working", ["coworking"], 120000, 1500, 6000, "verified"),
    ("Clarity Diagnostics", ["diagnostics", "clinic"], 40000, 300, 1500, "unverified"),
]
INTERESTS = {0: ["Jeevan Medicos", "Sanjeevani Chemists", "HealthFirst Pharmacy"], 3: ["Apna Kirana Mart"],
             9: ["Workbay Co-working"], 13: ["Pragati Classes"]}

FIRST = ["Aarav", "Vivaan", "Aditya", "Arjun", "Sai", "Ishaan", "Rohan", "Kabir", "Ananya", "Diya", "Isha", "Saanvi",
         "Aditi", "Kavya", "Meera", "Pooja", "Riya", "Sneha", "Priya", "Rahul", "Amit", "Sunil", "Vikas", "Deepak",
         "Manish", "Nikhil", "Sanjay", "Lakshmi", "Sunita", "Geeta", "Rekha", "Anjali", "Tanvi", "Harsh", "Yash",
         "Kunal", "Gaurav", "Farhan", "Zoya", "Imran"]
LAST = ["Sharma", "Verma", "Gupta", "Agrawal", "Jain", "Tomar", "Singh", "Yadav", "Kushwah", "Rathore", "Mishra",
        "Dubey", "Tiwari", "Bhadoria", "Saxena", "Shrivastava", "Chauhan", "Pandey", "Khan", "Joshi"]


def _offset(lat: float, lng: float, north_m: float, east_m: float) -> tuple[float, float]:
    return lat + north_m / 111320.0, lng + east_m / (111320.0 * math.cos(math.radians(lat)))


def _name() -> str:
    return f"{R.choice(FIRST)} {R.choice(LAST)}"


def _photo(seed: int, variant: int) -> bytes:
    """Synthetic listing photo: three compositions, textured so it reads as sharp, unique per seed."""
    rng = random.Random(seed)
    w, h = 960, 640
    wall = tuple(rng.randint(120, 230) for _ in range(3))
    accent = rng.choice([(251, 36, 98), (253, 152, 51), (0, 4, 237), (122, 244, 68), (40, 40, 40)])
    img = Image.new("RGB", (w, h), (200, 214, 222))
    d = ImageDraw.Draw(img)
    if variant == 0:  # shopfront
        d.rectangle([0, 0, w, int(h * 0.18)], fill=(170, 200, 225))
        d.rectangle([60, 90, w - 60, h - 110], fill=wall)
        d.rectangle([60, 90, w - 60, 170], fill=accent)
        shade = tuple(max(0, c - 45) for c in wall)
        for x in range(120, w - 120, 18):
            d.line([x, 200, x, h - 130], fill=shade, width=3)
        d.rectangle([0, h - 110, w, h], fill=(90, 90, 92))
    elif variant == 1:  # interior
        d.rectangle([0, 0, w, int(h * 0.62)], fill=wall)
        tile = rng.randint(48, 80)
        for y in range(int(h * 0.62), h, tile // 2):
            for x in range(0, w, tile):
                s = rng.randint(150, 205)
                d.rectangle([x, y, x + tile - 3, y + tile // 2 - 3], fill=(s, s, s - 10))
        d.rectangle([int(w * 0.35), int(h * 0.1), int(w * 0.65), int(h * 0.5)], fill=(215, 235, 245))
    else:  # street
        d.polygon([(int(w * 0.42), int(h * 0.45)), (int(w * 0.58), int(h * 0.45)), (w, h), (0, h)], fill=(96, 96, 98))
        for i in range(8):
            x0 = i * w // 8
            top = rng.randint(int(h * 0.12), int(h * 0.35))
            d.rectangle([x0, top, x0 + w // 8 - 6, int(h * 0.5)], fill=tuple(rng.randint(110, 220) for _ in range(3)))
    for _ in range(160):
        x, y, r, c = rng.randint(0, w), rng.randint(0, h), rng.randint(2, 10), rng.randint(30, 240)
        d.ellipse([x, y, x + r, y + r], fill=(c, c, c))
    img = Image.blend(img, Image.effect_noise((w, h), 30).convert("RGB"), 0.12)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    return buf.getvalue()


PHOTO_DIR = Path(__file__).parent / "seed_photos"


def _listing_photos(ptype: str, n: int, count: int = 3) -> list[bytes]:
    """Real photos for a listing of this type (rotated per listing so neighbours differ). Small pools get a
    mirrored, re-cropped variant so every photo stays distinct. Falls back to synthetic photos if none are bundled."""
    pool = sorted((PHOTO_DIR / ptype).glob("*.jpg")) or sorted((PHOTO_DIR / "shop").glob("*.jpg"))
    if not pool:
        return [_photo(n * 10 + v, v) for v in range(count)]
    out = []
    for v in range(count):
        img = Image.open(pool[(n + v) % len(pool)]).convert("RGB")
        if v >= len(pool):
            img = ImageOps.mirror(img)
            w, h = img.size
            img = img.crop((int(w * 0.12), int(h * 0.08), w, h))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=90)
        out.append(buf.getvalue())
    return out


def refresh_photos(db) -> int:
    """Replace every listing's photos with the bundled real photos for its type (keeps everything else)."""
    storage = get_storage()
    props = db.scalars(select(Property).order_by(Property.created_at)).all()
    seen: dict[str, int] = {}
    for p in props:
        n = seen[p.type] = seen.get(p.type, -1) + 1  # rotate within each type so covers differ
        count = max(len(p.media), 1)
        for m in list(p.media):
            for key in (m.storage_key, m.thumb_key):
                try:
                    storage.delete(key)
                except Exception:
                    pass
        p.media.clear()
        db.flush()
        for data in _listing_photos(p.type, n, count):
            p.media.append(media.process_upload(p, data, "image/jpeg", list(p.media)))
        db.flush()
        media.evaluate_quality(p)
    db.commit()
    return len(props)


def _support_time(published, now, recent_bias: float):
    start = published + timedelta(hours=2)
    recent_start = max(start, now - timedelta(days=14))
    end = now - timedelta(minutes=10)
    if R.random() < recent_bias or recent_start <= start:
        return recent_start + (end - recent_start) * R.random()
    return start + (recent_start - start) * R.random()


def reset(db) -> None:
    names = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables))
    db.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    db.commit()
    if settings.storage_backend == "local":
        shutil.rmtree(Path(settings.media_root) / "properties", ignore_errors=True)


def _user(db, *, name, roles, home=None, area=None, phone=None, email=None, created=None, seen=None, role=None):
    now = utcnow()
    u = User(name=name, phone=phone, email=email, phone_verified=bool(phone), email_verified=bool(email),
             active_role=role or roles[0], onboarded=True, created_at=created or now - timedelta(days=R.uniform(40, 200)))
    u.last_seen_at = seen or min(now, u.created_at + timedelta(days=R.uniform(0, 160)))
    if home:
        u.home_lat, u.home_lng = home
        u.home_label, u.home_area_id = (area.name, area.id) if area else (None, None)
    u.roles = [UserRole(role=r) for r in roles]
    db.add(u)
    return u


def seed(db) -> dict:
    now = utcnow()
    areas: dict[str, OpportunityArea] = {}
    for slug, (name, lat, lng, radius, footfall, transit, road, notes, comp) in AREAS.items():
        areas[slug] = OpportunityArea(slug=slug, name=name, city=CITY, lat=lat, lng=lng, radius_m=radius, stats={
            "competition": comp, "access": {"transit": transit, "road": road, "footfall_index": footfall, "notes": notes}})
    db.add_all(areas.values())
    db.flush()

    def home_near(slug, spread=450):
        a = areas[slug]
        return _offset(a.lat, a.lng, R.gauss(0, spread), R.gauss(0, spread))

    gp = areas["gol-pahadiya"]
    asha = _user(db, name="Asha Verma", roles=["resident"], phone="+919800000001", home=home_near("gol-pahadiya", 120),
                 area=gp, created=now - timedelta(days=95), seen=now)
    rajesh = _user(db, name="Rajesh Gupta", roles=["owner", "resident"], phone="+919800000002",
                   home=home_near("gol-pahadiya", 300), area=gp, created=now - timedelta(days=80), seen=now)
    neha = _user(db, name="Neha Sharma", roles=["business", "resident"], phone="+919800000003",
                 home=home_near("city-centre", 300), area=areas["city-centre"], created=now - timedelta(days=60), seen=now)
    admin_email = (settings.admin_email_list or ["admin@bizyukti.in"])[0]
    _user(db, name="BizYukti Team", roles=["admin", "resident"], email=admin_email, created=now - timedelta(days=120),
          seen=now, role="admin")

    slugs = list(AREAS)
    weights = [HOME_WEIGHTS.get(s, 1) for s in slugs]
    residents = [asha]
    for i in range(320):
        slug = R.choices(slugs, weights)[0]
        residents.append(_user(db, name=_name(), roles=["resident"], email=f"resident{i + 1}@example.com",
                               home=home_near(slug), area=areas[slug]))
    owners = {"rajesh": rajesh}
    for i in range(1, 21):
        slug = R.choice(slugs)
        owners[i] = _user(db, name=_name(), roles=["owner", "resident"], email=f"owner{i}@example.com",
                          home=home_near(slug), area=areas[slug])
    db.flush()

    businesses: dict[str, BusinessProfile] = {}
    for i, (bname, cats, budget, smin, smax, ver) in enumerate(BUSINESSES):
        u = neha if i == 0 else _user(db, name=_name(), roles=["business", "resident"], email=f"business{i}@example.com",
                                      home=home_near("city-centre", 900), area=areas["city-centre"])
        db.flush()
        b = BusinessProfile(user_id=u.id, name=bname, categories=cats, preferred_cities=[CITY], budget_min=budget // 3,
                            budget_max=budget, size_min_sqft=smin, size_max_sqft=smax, verification_status=ver,
                            registration_id=f"23AAB{'CDEFGHIJKLMN'[i]}{1234 + i}C1Z{i % 9}" if ver != "unverified" else None)
        db.add(b)
        businesses[bname] = b
    db.flush()
    brew = businesses["Brewline Café"]
    db.add(Verification(subject_type="business", subject_id=brew.id, kind="kyb", submitted_by=brew.user_id,
                        evidence={"registration_id": brew.registration_id, "website": None, "name": brew.name}))

    demands: list[Demand] = []
    for idx, (slug, cat, title, target, reason, days, bias, author_key) in enumerate(DEMANDS):
        a = areas[slug]
        lat, lng = (a.lat, a.lng) if idx == 0 else _offset(a.lat, a.lng, R.gauss(0, 160), R.gauss(0, 160))
        near = [u for u in residents if u is not asha and haversine_m(u.home_lat, u.home_lng, lat, lng) <= 4600]
        R.shuffle(near)
        author = asha if author_key and author_key.startswith("asha") else near.pop()
        published = now - timedelta(days=days, hours=R.uniform(0, 10))
        d = Demand(author_id=author.id, title=title, category=cat, reason=reason, lat=lat, lng=lng, locality=a.name,
                   area_id=a.id, status="published", verification_status="pending", tags=[],
                   ai_meta={"confidence": 0.95, "source": "seed"}, published_at=published, created_at=published,
                   expires_at=published + timedelta(days=180))
        db.add(d)
        db.flush()
        chosen = near[: max(0, target - 1)]
        if idx in (0, 2) and author is not asha:
            chosen = [asha] + [u for u in chosen if u is not asha][: target - 2]
        rows = [DemandSupport(demand_id=d.id, user_id=author.id, status="verified", distance_m=0.0,
                              device_hash=keyed_hash(f"seed-{author.id}", "device"), created_at=published, verified_at=published)]
        for u in chosen:
            t = _support_time(published, now, bias)
            if u is asha:
                t = now - (timedelta(days=3) if idx == 0 else timedelta(hours=5))
            rows.append(DemandSupport(demand_id=d.id, user_id=u.id, status="verified", created_at=t, verified_at=t,
                                      distance_m=haversine_m(u.home_lat, u.home_lng, lat, lng),
                                      device_hash=keyed_hash(f"seed-{u.id}", "device")))
        db.add_all(rows)
        d.last_support_at = max(r.created_at for r in rows)
        db.flush()
        trust.evaluate_demand(db, d)
        for r in rows:
            if r.user_id == asha.id and author is not asha:
                e = rewards.award(db, asha.id, "demand_supported", "support", r.id)
                if e:
                    e.created_at, e.expected_unlock_at = r.created_at, r.created_at + timedelta(hours=24)
        if author is asha:
            e = rewards.award(db, asha.id, "demand_published", "demand", d.id)
            if e:
                e.created_at, e.expected_unlock_at = published, published + timedelta(hours=48)
        if author_key == "asha:fulfilled":
            demand_svc.fulfil(db, d, asha)
            d.fulfilled_at = now - timedelta(days=10)
        demands.append(d)
    db.flush()

    for idx, names in INTERESTS.items():
        d = demands[idx]
        for bname in names:
            db.add(DemandInterest(demand_id=d.id, user_id=businesses[bname].user_id, note="Exploring a new outlet here",
                                  created_at=d.published_at + timedelta(days=R.uniform(2, 9))))
        db.flush()
        trust.evaluate_demand(db, d)

    risky = _user(db, name="Rohit K", roles=["resident"], email="newcomer@example.com", home=home_near("padav", 200),
                  area=areas["padav"], created=now - timedelta(minutes=20), seen=now)
    db.flush()
    demand_svc.create_demand(db, risky, text_in="Tiffin service, WhatsApp me for daily orders", description=None,
                             category=None, reason="daily_need", reason_note=None, lat=risky.home_lat, lng=risky.home_lng,
                             publish=True, device=None, client_lat=None, client_lng=None)

    props: list[Property] = []
    type_seen: dict[str, int] = {}
    for n, (slug, north, east, ptype, size, unit, ptype_price, amount, negotiable, avail_in, desc, amen, okey, verified) \
            in enumerate(PROPERTIES):
        a = areas[slug]
        lat, lng = _offset(a.lat, a.lng, north, east)
        published = now - timedelta(days=R.uniform(3, 50))
        owner = owners[okey]
        p = Property(owner_id=owner.id, type=ptype, size_value=size, size_unit=unit,
                     size_sqft=round(size * (10.7639 if unit == "sqm" else 1.0), 1), price_type=ptype_price,
                     price_amount=amount, price_negotiable=negotiable, availability="future" if avail_in else "now",
                     available_from=(now + timedelta(days=avail_in)).date() if avail_in else None, lat=lat, lng=lng,
                     address=f"Shop {R.randint(3, 180)}, {a.name} main road, {CITY}", locality=a.name, area_id=a.id,
                     description=desc, amenities=amen, status="published", published_at=published, created_at=published,
                     last_confirmed_at=now - timedelta(days=35 if (okey == "rajesh" and ptype == "office") else R.uniform(0, 20)),
                     verification_status="verified" if verified else "unverified",
                     verification_level="documents" if verified else "basic")
        db.add(p)
        db.flush()
        type_n = type_seen[ptype] = type_seen.get(ptype, -1) + 1  # rotate within each type so covers differ
        for data in _listing_photos(ptype, type_n):
            p.media.append(media.process_upload(p, data, "image/jpeg", list(p.media)))
        db.flush()
        media.evaluate_quality(p)
        props.append(p)
    draft = Property(owner_id=rajesh.id, type="warehouse", size_value=3000, size_unit="sqft", size_sqft=3000,
                     lat=_offset(areas["dd-nagar"].lat, areas["dd-nagar"].lng, -350, -300)[0],
                     lng=_offset(areas["dd-nagar"].lat, areas["dd-nagar"].lng, -350, -300)[1],
                     locality="DD Nagar", area_id=areas["dd-nagar"].id, status="draft", price_type="rent")
    db.add(draft)
    db.flush()
    draft.media.append(media.process_upload(draft, _listing_photos("warehouse", 99, 1)[0], "image/jpeg", []))
    db.flush()
    media.evaluate_quality(draft)

    for p in props:
        if p.owner_id == rajesh.id:
            e = rewards.award(db, rajesh.id, "property_listed", "property", p.id)
            if e:
                e.created_at, e.expected_unlock_at = p.published_at, p.published_at + timedelta(hours=72)
            if p.verification_status == "verified":
                rewards.award(db, rajesh.id, "property_verified", "property", p.id)
    pending_doc = props[8]
    pending_doc.verification_status = "pending"
    db.add(Verification(subject_type="property", subject_id=pending_doc.id, kind="ownership_document",
                        submitted_by=pending_doc.owner_id,
                        evidence={"document_type": "Property tax receipt", "note": "Receipt is in my father's name"}))
    db.flush()

    for p in props:
        matching.recompute_for_property(db, p.id, notify_owner=p.owner_id == rajesh.id)
    db.flush()

    shop, office = props[0], props[13]
    flagship = demands[0]
    db.execute(Match.__table__.update().where(Match.property_id == shop.id, Match.demand_id == flagship.id)
               .values(status="contacted"))
    t1 = Inquiry(from_user_id=neha.id, to_user_id=rajesh.id, kind="space", property_id=shop.id, demand_id=flagship.id,
                 subject="Interest in your 850 sq ft shop", status="replied", created_at=now - timedelta(days=2),
                 last_message_at=now - timedelta(days=1))
    t1.messages = [
        Message(sender_id=neha.id, body="Hi, we're planning a pharmacy near Gol Pahadiya. Is the shop available from "
                                        "next month, and could we visit this week?", created_at=now - timedelta(days=2),
                read_at=now - timedelta(days=2)),
        Message(sender_id=rajesh.id, body="Yes, it's available now. Weekday evenings after 5 pm work for a visit.",
                created_at=now - timedelta(days=1)),
    ]
    workbay = businesses["Workbay Co-working"]
    t2 = Inquiry(from_user_id=workbay.user_id, to_user_id=rajesh.id, kind="space", property_id=office.id,
                 subject="Interest in your 1,400 sq ft office", created_at=now - timedelta(hours=6),
                 last_message_at=now - timedelta(hours=6))
    t2.messages = [Message(sender_id=workbay.user_id, body="Could this floor take 40 desks? We'd like to see it on "
                                                           "Saturday.", created_at=now - timedelta(hours=6))]
    t3 = Inquiry(from_user_id=brew.user_id, to_user_id=None, kind="market_brief", area_id=areas["city-centre"].id,
                 category="cafe", subject="Market brief: Café in City Centre, Gwalior", created_at=now - timedelta(days=1),
                 last_message_at=now - timedelta(days=1))
    t3.messages = [Message(sender_id=brew.user_id, body="We want footfall by hour and rent ranges for a 600 sq ft café.",
                           created_at=now - timedelta(days=1))]
    db.add_all([t1, t2, t3])
    db.add_all([SavedItem(user_id=neha.id, kind="area", ref_id=gp.id, category="pharmacy"),
                SavedItem(user_id=neha.id, kind="area", ref_id=areas["hazira"].id, category="pharmacy"),
                SavedItem(user_id=neha.id, kind="property", ref_id=shop.id)])
    db.flush()
    rewards.settle(db)
    db.commit()
    return {
        "areas": len(areas), "users": db.scalar(select(func.count(User.id))),
        "demands": db.scalar(select(func.count(Demand.id))), "supports": db.scalar(select(func.count(DemandSupport.id))),
        "properties": db.scalar(select(func.count(Property.id))), "matches": db.scalar(select(func.count(Match.id))),
        "rewards": db.scalar(select(func.count(RewardLedger.id))),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="delete all data first")
    parser.add_argument("--if-empty", action="store_true", help="only seed when the database has no areas")
    parser.add_argument("--refresh-photos", action="store_true", help="replace listing photos with the bundled real photos")
    args = parser.parse_args()
    if settings.is_production:
        sys.exit("Refusing to seed demo data in production.")
    with SessionLocal() as db:
        if args.refresh_photos:
            print(f"Refreshed photos on {refresh_photos(db)} listings.")
            return
        has_data = db.scalar(select(func.count(OpportunityArea.id)))
        if has_data and args.if_empty:
            print("Database already has data; skipping seed.")
            return
        if has_data and not args.reset:
            sys.exit("Database already has data. Run with --reset to replace it.")
        if args.reset:
            reset(db)
        counts = seed(db)
    print("Seeded demo data:", ", ".join(f"{k}={v}" for k, v in counts.items()))
    print("Demo sign-in (codes are shown on screen while OTP_DEV_ECHO=true):")
    print("  resident  +91 98000 00001   owner  +91 98000 00002   business  +91 98000 00003")
    print(f"  admin     {(settings.admin_email_list or ['admin@bizyukti.in'])[0]}  (set ADMIN_EMAILS to match)")


if __name__ == "__main__":
    main()

"""Business categories, the deterministic classifier, and the space-fit rules used by matching.
The rule-based classifier always runs; an optional LLM pass (services/ai.py) only refines
low-confidence results, so categorisation never depends on an external provider."""

import math
import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Category:
    slug: str
    name: str
    noun: str  # used in sentences: "184 residents asked for a pharmacy"
    why: str  # "Why it matters" default copy
    types: tuple[str, ...]  # suitable property types
    size: tuple[int, int]  # typical sq ft range
    keywords: tuple[str, ...] = field(default=())


CATEGORIES: list[Category] = [
    Category("pharmacy", "Pharmacy", "a pharmacy", "daily medicine access", ("shop",), (150, 1000),
             ("pharmacy", "chemist", "medical store", "medicine", "medicines", "dawai", "dawa", "drug store", "medicals")),
    Category("grocery", "Grocery store", "a grocery store", "everyday groceries within walking distance", ("shop", "warehouse"), (200, 3000),
             ("grocery", "groceries", "kirana", "supermarket", "general store", "provision", "vegetable", "vegetables", "sabzi", "fruits", "dairy", "milk", "mart")),
    Category("cafe", "Café", "a café", "a place to meet and work nearby", ("shop", "office"), (300, 1500),
             ("cafe", "café", "coffee", "chai", "tea stall", "tea shop", "bistro")),
    Category("restaurant", "Restaurant", "a restaurant", "good food without a long drive", ("shop",), (600, 3000),
             ("restaurant", "dhaba", "eatery", "thali", "biryani", "family restaurant", "food court", "dining")),
    Category("bakery", "Bakery", "a bakery", "fresh bread and cakes close by", ("shop",), (200, 1000),
             ("bakery", "cake", "cakes", "bread", "pastry", "confectionery")),
    Category("gym", "Gym", "a gym", "fitness close to home", ("shop", "office", "warehouse"), (1200, 5000),
             ("gym", "fitness", "workout", "crossfit", "yoga", "zumba")),
    Category("salon", "Salon", "a salon", "grooming close to home", ("shop",), (250, 1200),
             ("salon", "parlour", "parlor", "barber", "haircut", "beauty", "spa", "unisex")),
    Category("clinic", "Clinic", "a clinic", "a doctor within reach", ("shop", "office"), (300, 2000),
             ("clinic", "doctor", "physician", "dentist", "dental", "pediatric", "paediatric", "physiotherapy", "physio", "nursing home")),
    Category("diagnostics", "Diagnostic lab", "a diagnostic lab", "medical tests without crossing the city", ("shop", "office"), (300, 1500),
             ("diagnostic", "diagnostics", "pathology", "blood test", "x-ray", "xray", "scan centre", "lab test")),
    Category("coaching", "Coaching centre", "a coaching centre", "learning close to home for students", ("office", "shop"), (400, 2500),
             ("coaching", "tuition", "tuitions", "classes", "academy", "institute", "spoken english", "computer classes")),
    Category("daycare", "Daycare", "a daycare", "safe childcare for working parents", ("shop", "office", "other"), (800, 3000),
             ("daycare", "day care", "creche", "crèche", "playschool", "play school", "preschool", "kindergarten")),
    Category("bookstore", "Bookstore", "a bookstore", "books and stationery nearby", ("shop",), (200, 1200),
             ("book", "books", "bookstore", "bookshop", "stationery", "library")),
    Category("hardware", "Hardware store", "a hardware store", "repairs without a trip to the market", ("shop", "warehouse"), (300, 2000),
             ("hardware", "paint", "electrical", "plumbing", "sanitary", "tools")),
    Category("electronics", "Mobile & electronics", "a phone and electronics shop", "phone and device repairs nearby", ("shop",), (120, 800),
             ("mobile", "phone", "repair", "electronics", "laptop", "recharge")),
    Category("laundry", "Laundry", "a laundry", "laundry and ironing nearby", ("shop",), (150, 800),
             ("laundry", "dry clean", "dry cleaning", "dry cleaner", "dhobi", "ironing", "press wala")),
    Category("bank_atm", "Bank or ATM", "a bank or ATM", "cash and banking access", ("shop", "office"), (80, 2000),
             ("atm", "bank", "cash machine", "branch")),
    Category("pet_care", "Pet care", "pet care", "pet supplies and vet care nearby", ("shop",), (200, 1200),
             ("pet", "pets", "vet", "veterinary", "pet shop", "dog", "cat")),
    Category("coworking", "Co-working space", "a co-working space", "a workspace without a long commute", ("office",), (1000, 6000),
             ("coworking", "co-working", "shared office", "workspace", "hot desk")),
    Category("sports", "Sports & turf", "a sports turf", "a place to play nearby", ("land", "warehouse", "other"), (3000, 20000),
             ("turf", "sports", "badminton", "football", "cricket", "swimming", "court", "box cricket")),
    Category("delivery_hub", "Delivery hub", "a delivery hub", "faster deliveries to the locality", ("warehouse", "shop", "land"), (1500, 10000),
             ("delivery", "dark store", "quick commerce", "logistics", "courier")),
    Category("other", "Other business", "this business", "something the locality is missing", ("shop", "office", "land", "warehouse", "other"), (100, 10000), ()),
]

BY_SLUG: dict[str, Category] = {c.slug: c for c in CATEGORIES}
PROPERTY_TYPES = {"shop": "shop", "office": "office", "land": "plot", "warehouse": "warehouse", "other": "space"}
REASONS = {
    "daily_need": "Daily need",
    "commute": "On my commute",
    "students": "For students",
    "family": "For families",
    "other": "Other",
}
AMENITIES = {
    "ground_floor": "Ground floor",
    "road_facing": "Road facing",
    "parking": "Parking",
    "washroom": "Washroom",
    "power_backup": "Power backup",
    "water": "Water connection",
    "storage": "Storage room",
    "three_phase": "3-phase power",
}

_LEADING = re.compile(
    r"^\s*(please\s+)?((i|we)\s+(really\s+)?(want|need|would\s+like|wish\s+for|miss)|there\s+should\s+be|need|want|open|we\s+need)"
    r"\s+(a|an|the|some|more)?\s*",
    re.IGNORECASE,
)


def get(slug: str) -> Category:
    return BY_SLUG.get(slug, BY_SLUG["other"])


def clean_title(text: str) -> str:
    """'I want a bookstore near the park' -> 'Bookstore near the park'"""
    t = _LEADING.sub("", text.strip()).strip(" .!")
    t = re.sub(r"\s+", " ", t)[:80]
    return (t[:1].upper() + t[1:]) if t else text.strip()[:80]


def _normalise(text: str) -> str:
    return " " + re.sub(r"[^a-z0-9éè\- ]+", " ", text.lower()) + " "


def classify(text: str) -> tuple[str, float, list[str]]:
    """Returns (category slug, confidence 0..1, matched keywords)."""
    norm = _normalise(text)
    scored: list[tuple[float, str, list[str]]] = []
    for cat in CATEGORIES:
        hits = [k for k in cat.keywords if f" {k} " in norm]
        if hits:
            scored.append((sum(1 + 0.25 * k.count(" ") for k in hits), cat.slug, hits))
    if not scored:
        return "other", 0.0, []
    scored.sort(reverse=True)
    best, slug, hits = scored[0]
    second = scored[1][0] if len(scored) > 1 else 0.0
    confidence = 0.95 if second == 0 else round(min(0.9, best / (best + second)), 2)
    return slug, confidence, hits[:5]


def suitability(category: str, prop_type: str, size_sqft: float | None) -> tuple[float, float]:
    """(type fit, size fit) both 0..1. Type fit 0 means the space cannot host the category."""
    cat = get(category)
    if prop_type in cat.types:
        type_fit = 1.0
    elif prop_type == "other":
        type_fit = 0.4
    else:
        return 0.0, 0.0
    if not size_sqft:
        return type_fit, 0.5
    lo, hi = cat.size
    if lo <= size_sqft <= hi:
        return type_fit, 1.0
    ratio = size_sqft / lo if size_sqft < lo else hi / size_sqft
    return type_fit, round(max(0.0, 1 - 1.6 * (1 - ratio)), 3)


def size_window(category: str) -> tuple[float, float]:
    lo, hi = get(category).size
    return lo * 0.6, hi * 1.6


def suggest_property_type(size_sqft: float | None, description: str = "") -> str:
    text = description.lower()
    for word, kind in (("warehouse", "warehouse"), ("godown", "warehouse"), ("plot", "land"), ("land", "land"),
                       ("office", "office"), ("shop", "shop"), ("showroom", "shop")):
        if word in text:
            return kind
    if not size_sqft:
        return "shop"
    if size_sqft >= 8000:
        return "land"
    if size_sqft >= 3000:
        return "warehouse"
    return "shop"


def demand_strength(supporters: int, saturation: int = 200) -> float:
    return min(1.0, math.log1p(max(0, supporters)) / math.log1p(saturation))


def public_list() -> list[dict]:
    return [
        {"slug": c.slug, "name": c.name, "noun": c.noun, "why": c.why, "types": list(c.types),
         "size_min": c.size[0], "size_max": c.size[1]}
        for c in CATEGORIES
    ]

"""Test setup: a dedicated Postgres+PostGIS database migrated with Alembic, eager jobs,
echoed one-time codes and an in-memory rate limiter. Tables are truncated before each test."""

import io
import itertools
import os
import random
import tempfile

TMP = tempfile.mkdtemp(prefix="bizyukti-test-")
os.environ.update({
    "ENV": "test",
    "DATABASE_URL": os.environ.get("TEST_DATABASE_URL",
                                   "postgresql+psycopg://bizyukti:bizyukti@localhost:5432/bizyukti_test"),
    "REDIS_URL": "", "TASKS_EAGER": "true", "OTP_DEV_ECHO": "true", "STORAGE_BACKEND": "local",
    "MEDIA_ROOT": os.path.join(TMP, "media"), "ADMIN_EMAILS": "admin@test.in",
    "SECRET_KEY": "test-secret-key-0123456789abcdef0123456789",
})

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import OpportunityArea  # noqa: E402
from app.ratelimit import limiter  # noqa: E402

API = "/api/v1"
BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GP = (26.2330, 78.1590)  # Gol Pahadiya
AREAS = [("gol-pahadiya", "Gol Pahadiya", 26.2330, 78.1590, {"pharmacy": 1}, 0.78),
         ("thatipur", "Thatipur", 26.2185, 78.2110, {}, 0.6),
         ("city-centre", "City Centre", 26.2075, 78.1960, {}, 0.6)]


@pytest.fixture(scope="session", autouse=True)
def _schema():
    cfg = Config(os.path.join(BACKEND, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BACKEND, "alembic"))
    command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
def _clean():
    names = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables))
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    limiter.reset()
    with SessionLocal() as db:
        db.add_all([OpportunityArea(slug=s, name=n, city="Gwalior", lat=lat, lng=lng, radius_m=1500,
                                    stats={"competition": comp, "access": {"transit": "high", "footfall_index": ff}})
                    for s, n, lat, lng, comp, ff in AREAS])
        db.commit()


@pytest.fixture
def client():
    return TestClient(app)


def login(client, destination: str, channel: str = "phone", device: str | None = None) -> dict:
    r = client.post(f"{API}/auth/otp/request", json={"channel": channel, "destination": destination})
    assert r.status_code == 200, r.text
    headers = {"X-Device-Id": device or f"device-{destination}"}
    r = client.post(f"{API}/auth/otp/verify", headers=headers,
                    json={"channel": channel, "destination": destination, "code": r.json()["dev_code"]})
    assert r.status_code == 200, r.text
    return {**headers, "Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def make_user(client):
    counter = itertools.count(1)

    def _make(role="resident", lat=GP[0], lng=GP[1], business=None, device=None):
        n = next(counter)
        h = login(client, f"98765{n:05d}", device=device)
        body = {"name": f"User {n}", "role": role, "home": {"lat": lat, "lng": lng}}
        if business:
            body["business"] = business
        r = client.post(f"{API}/me/onboarding", json=body, headers=h)
        assert r.status_code == 200, r.text
        return h

    return _make


def photo(seed: int, blur: float = 0, size=(800, 600)) -> bytes:
    rng = random.Random(seed)
    img = Image.effect_noise(size, 40).convert("RGB")
    d = ImageDraw.Draw(img)
    for _ in range(30):
        x, y = rng.randint(0, size[0]), rng.randint(0, size[1])
        d.rectangle([x, y, x + rng.randint(20, 220), y + rng.randint(20, 220)],
                    fill=tuple(rng.randint(0, 255) for _ in range(3)))
    if blur:
        img = img.filter(ImageFilter.GaussianBlur(blur))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()


def verified_demand(client, make_user, supporters: int = 3, text_in: str = "We need a medical store") -> tuple[str, dict]:
    author = make_user()
    r = client.post(f"{API}/demands", headers=author,
                    json={"text": text_in, "reason": "daily_need", "lat": GP[0], "lng": GP[1]})
    assert r.status_code == 201, r.text
    did = r.json()["demand"]["id"]
    for i in range(supporters):
        s = make_user(lat=GP[0] + 0.002 * (i + 1), lng=GP[1])
        assert client.post(f"{API}/demands/{did}/support", headers=s).json()["support"]["status"] == "verified"
    return did, author


def published_space(client, make_user, owner=None, **overrides) -> tuple[str, dict]:
    owner = owner or make_user(role="owner")
    body = {"type": "shop", "size_value": 79, "size_unit": "sqm", "lat": GP[0] + 0.003, "lng": GP[1] + 0.002,
            "price_type": "rent", "price_amount": 28000, "address": "Shop 12, main road",
            "description": "Ground-floor shop on the main road with a wide shutter."} | overrides
    r = client.post(f"{API}/properties", json=body, headers=owner)
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    for seed in (11, 12, 13):
        up = client.post(f"{API}/properties/{pid}/media", headers=owner,
                         files={"file": ("p.jpg", photo(seed), "image/jpeg")})
        assert up.status_code == 201, up.text
    r = client.post(f"{API}/properties/{pid}/publish", headers=owner)
    assert r.status_code == 200, r.text
    return pid, owner

"""End-to-end product flows across the three sides of the marketplace."""

from datetime import timedelta

from sqlalchemy import update

from app.db import SessionLocal
from app.models import RewardLedger
from app.security import utcnow

from .conftest import API, GP, login, photo, published_space, verified_demand


def test_resident_demand_lifecycle_with_trust_rules(client, make_user):
    author = make_user()
    hint = client.post(f"{API}/demands/assist", json={"text": "We need a medical store", "lat": GP[0], "lng": GP[1]},
                       headers=author).json()
    assert hint["category"] == "pharmacy" and hint["title"] == "Medical store"
    r = client.post(f"{API}/demands", headers=author,
                    json={"text": "We need a medical store", "reason": "daily_need", "lat": GP[0], "lng": GP[1]})
    assert r.status_code == 201, r.text
    d = r.json()["demand"]
    did = d["id"]
    assert d["locality"] == "Gol Pahadiya" and d["status"] == "published" and not d["verified"]
    assert d["display_title"] == "Medical store near Gol Pahadiya" and d["supporters"] == 1

    other = make_user()
    dup = client.post(f"{API}/demands", headers=other,
                      json={"text": "pharmacy please", "lat": GP[0] + 0.001, "lng": GP[1], "reason": "daily_need"})
    assert dup.status_code == 409 and dup.json()["code"] == "duplicate" and dup.json()["similar"][0]["id"] == did

    far = make_user(lat=26.31, lng=78.31)
    assert client.post(f"{API}/demands/{did}/support", headers=far).json()["support"]["status"] == "rejected"
    a = make_user(device="shared-phone")
    b = make_user(device="shared-phone")
    assert client.post(f"{API}/demands/{did}/support", headers=a).json()["support"]["status"] == "verified"
    second = client.post(f"{API}/demands/{did}/support", headers=b).json()["support"]
    assert second["status"] == "rejected" and "device" in second["reason"]

    for i in range(2):
        s = make_user(lat=GP[0] + 0.003 * (i + 1), lng=GP[1])
        client.post(f"{API}/demands/{did}/support", headers=s)
    detail = client.get(f"{API}/demands/{did}").json()
    assert detail["verified"] and detail["supporters"] == 4 and detail["status"] == "published"

    for i in range(6):
        s = make_user(lat=GP[0], lng=GP[1] + 0.002 * (i + 1))
        client.post(f"{API}/demands/{did}/support", headers=s)
    assert client.get(f"{API}/demands/{did}").json()["status"] == "growing"

    summary = client.get(f"{API}/rewards", headers=author).json()
    assert summary["balance"] == 30 and summary["pending"] == 20
    with SessionLocal() as db:
        db.execute(update(RewardLedger).values(expected_unlock_at=utcnow() - timedelta(minutes=1)))
        db.commit()
    summary = client.get(f"{API}/rewards", headers=author).json()
    assert summary["balance"] == 50 and summary["pending"] == 0
    assert client.post(f"{API}/rewards/redeem", json={"offer_id": "partner-coffee"}, headers=author).status_code == 409

    mine = client.get(f"{API}/demands/mine", headers=author).json()
    assert mine["created"][0]["id"] == did
    assert client.post(f"{API}/demands/{did}/share").json()["url"].endswith(f"/demands/{did}")


def test_owner_listing_media_checks_publish_and_matches(client, make_user):
    did, _ = verified_demand(client, make_user)
    owner = make_user(role="owner")
    r = client.post(f"{API}/properties", headers=owner, json={
        "type": "shop", "size_value": 79, "size_unit": "sqm", "lat": GP[0] + 0.003, "lng": GP[1] + 0.002,
        "price_type": "rent", "price_amount": 28000, "address": "Shop 12, main road",
        "description": "Ground-floor shop on the main road with a wide shutter."})
    assert r.status_code == 201 and round(r.json()["size_sqft"]) == 850
    pid = r.json()["id"]
    blocked = client.post(f"{API}/properties/{pid}/publish", headers=owner)
    assert blocked.status_code == 422 and "3 photos" in blocked.json()["missing"]

    def up(data):
        return client.post(f"{API}/properties/{pid}/media", headers=owner, files={"file": ("p.jpg", data, "image/jpeg")})

    first = up(photo(1))
    assert first.status_code == 201 and first.json()["warning"] is None
    assert up(photo(1)).json()["media"]["is_duplicate"]
    assert up(photo(2, blur=8)).json()["media"]["is_blurry"]
    assert up(b"not an image").status_code == 422
    last = up(photo(3)).json()
    assert last["good_photos"] == 3 and last["blockers"] == []

    pub = client.post(f"{API}/properties/{pid}/publish", headers=owner)
    assert pub.status_code == 200 and pub.json()["status"] == "published" and pub.json()["reward"]["points"] == 25
    matches = client.get(f"{API}/properties/{pid}/matches", headers=owner).json()["items"]
    top = matches[0]
    assert top["demand"]["id"] == did and top["score"] >= 70
    assert top["summary"].startswith("Matched because 4 nearby residents requested a pharmacy")
    assert top["density"]["label"] in ("Low", "Medium", "High")
    home = client.get(f"{API}/properties/mine", headers=owner).json()
    assert home["spaces"][0]["top_demand"]["category"] == "pharmacy" and home["new_matches_week"] >= 1
    assert client.get(f"{API}/demands/{did}").json()["matched_spaces"] == 1
    public = client.get(f"{API}/properties/{pid}").json()
    assert "address" not in public and public["demand_density"]["supporters"] == 4
    notes = client.get(f"{API}/notifications", headers=owner).json()
    assert any(n["kind"] == "match.created" for n in notes["items"])

    r = client.post(f"{API}/properties/{pid}/verification", headers=owner, data={"document_type": "Electricity bill"},
                    files={"file": ("bill.pdf", b"%PDF-1.4 test", "application/pdf")})
    assert r.status_code == 201
    admin = login(client, "admin@test.in", "email")
    item = next(i for i in client.get(f"{API}/admin/queue", headers=admin).json()["items"] if i["subject_type"] == "property")
    assert item["has_document"]
    assert client.get(f"{API}/admin/verifications/{item['id']}/document", headers=admin).content == b"%PDF-1.4 test"
    assert client.post(f"{API}/admin/verifications/{item['id']}/decide", json={"decision": "approve"},
                       headers=admin).status_code == 200
    assert client.get(f"{API}/properties/{pid}").json()["verified"]
    assert any(e["action"] == "property_verified" and e["status"] == "available"
               for e in client.get(f"{API}/rewards", headers=owner).json()["entries"])
    assert client.post(f"{API}/properties/{pid}/confirm", headers=owner).json()["recently_updated"]


def test_business_discovery_interest_and_conversations(client, make_user):
    did, _ = verified_demand(client, make_user)
    pid, owner = published_space(client, make_user)
    biz = make_user(role="business", business={"name": "CareWell Pharmacy", "categories": ["pharmacy"],
                                               "preferred_cities": ["Gwalior"], "budget_max": 40000})
    opp = client.get(f"{API}/opportunities", headers=biz).json()
    best = opp["areas"][0]
    assert opp["category"] == "pharmacy" and best["area"]["name"] == "Gol Pahadiya"
    assert best["supporters"] == 4 and best["spaces"] == 1 and best["reasons"][0].startswith("4 verified residents")
    area_id = best["area"]["id"]
    detail = client.get(f"{API}/opportunities/areas/{area_id}", headers=biz).json()
    assert detail["spaces"][0]["id"] == pid and len(detail["series"]) == 8 and detail["rank"] == 1
    layers = client.get(f"{API}/map/layers", params={"category": "pharmacy"}, headers=biz).json()
    assert layers["zones"][0]["supporters"] == 4 and layers["spaces"][0]["id"] == pid

    assert client.post(f"{API}/saved", json={"kind": "area", "ref_id": area_id, "category": "pharmacy"},
                       headers=biz).status_code == 201
    assert client.get(f"{API}/saved", headers=biz).json()["areas"][0]["category"] == "pharmacy"

    interest = client.post(f"{API}/demands/{did}/interest", json={"note": "Planning an outlet"}, headers=biz)
    assert interest.json()["demand"]["status"] == "matched"
    r = client.post(f"{API}/inquiries", headers=biz,
                    json={"kind": "space", "property_id": pid, "demand_id": did, "message": "Is it free next month?"})
    assert r.status_code == 201, r.text
    iid = r.json()["id"]
    received = client.get(f"{API}/inquiries", params={"box": "received"}, headers=owner).json()["items"]
    assert received[0]["unread"] == 1 and received[0]["context"]["property"]["id"] == pid
    client.post(f"{API}/inquiries/{iid}/messages", json={"body": "Yes, visit any evening."}, headers=owner)
    thread = client.get(f"{API}/inquiries/{iid}", headers=biz).json()
    assert thread["status"] == "replied" and [m["mine"] for m in thread["messages"]] == [True, False]

    det = client.get(f"{API}/demands/{did}", headers=owner).json()
    assert det["interested_businesses"] == 1 and det["businesses"][0]["name"] == "CareWell Pharmacy"
    r = client.post(f"{API}/inquiries", headers=owner, json={
        "kind": "business", "interest_id": det["businesses"][0]["interest_id"], "property_id": pid,
        "message": "My shop is 400 m from the requests."})
    assert r.status_code == 201

    brief = client.post(f"{API}/inquiries", headers=biz, json={"kind": "market_brief", "area_id": area_id,
                                                               "category": "pharmacy", "message": "Send a brief"})
    assert brief.status_code == 201 and brief.json()["with"]["name"] == "BizYukti team"
    admin = login(client, "admin@test.in", "email")
    team = client.get(f"{API}/inquiries", params={"box": "team"}, headers=admin).json()["items"]
    assert team[0]["kind"] == "market_brief"
    client.post(f"{API}/inquiries/{team[0]['id']}/messages", json={"body": "Brief attached by Friday."}, headers=admin)
    reply = client.get(f"{API}/inquiries/{team[0]['id']}", headers=biz).json()["messages"][-1]
    assert reply["sender"] == "BizYukti team"

    assert client.post(f"{API}/demands/{did}/fulfil", headers=biz).json()["status"] == "fulfilled"


def test_admin_review_moderation_and_kpis(client, make_user):
    risky = make_user()
    r = client.post(f"{API}/demands", headers=risky, json={
        "text": "Tiffin service, message me on whatsapp", "lat": GP[0], "lng": GP[1], "reason": "daily_need"})
    did = r.json()["demand"]["id"]
    assert client.get(f"{API}/admin/queue", headers=make_user()).status_code == 403
    admin = login(client, "admin@test.in", "email")
    queue = client.get(f"{API}/admin/queue", headers=admin).json()
    item = next(i for i in queue["items"] if i["subject_type"] == "demand")
    assert "Contains links or contact details" in item["subject"]["demand"]["risk_reasons"]
    assert client.post(f"{API}/admin/verifications/{item['id']}/decide", json={"decision": "reject", "reason": "Spam"},
                       headers=admin).json()["status"] == "rejected"
    assert client.get(f"{API}/demands/{did}").status_code == 404
    stats = client.get(f"{API}/admin/stats", headers=admin).json()
    assert {k["key"] for k in stats["kpis"]} >= {"publish_completion", "verified_support_rate", "match_to_inquiry",
                                                 "reward_abuse", "listing_freshness"}
    assert stats["totals"]["demands"] == 1


def test_validation_errors_are_friendly(client, make_user):
    h = make_user()
    r = client.post(f"{API}/demands", headers=h, json={"text": "x", "lat": 200, "lng": 0})
    assert r.status_code == 422 and r.json()["detail"].startswith("Check ")
    assert client.get(f"{API}/demands/not-a-uuid").status_code == 422
    assert client.get(f"{API}/demands/00000000-0000-0000-0000-000000000000").status_code == 404
    assert client.get("/health").json() == {"ok": True}
    assert client.get(f"{API}/ready").json()["checks"]["database"] == "ok"

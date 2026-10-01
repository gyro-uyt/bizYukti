"""Business decision reports: competitor gap analysis and financial feasibility."""

from tests.conftest import API, GP, published_space, verified_demand

BIZ = {"name": "CareWell Pharmacy", "categories": ["pharmacy"], "preferred_cities": ["Gwalior"], "budget_max": 40000}
VERDICTS = {"Wide gap", "Clear gap", "Narrow gap", "Crowded", "No proven demand yet"}


def _area_id(client, headers, slug_name="Gol Pahadiya"):
    return next(a["id"] for a in client.get(f"{API}/geo/areas").json() if a["name"] == slug_name)


def test_competitor_gap_explains_demand_vs_supply(client, make_user):
    verified_demand(client, make_user)  # "medical store" -> pharmacy, 4 verified supporters at Gol Pahadiya
    late = make_user(lat=GP[0] + 0.001, lng=GP[1])
    r = client.post(f"{API}/demands", headers=late, json={"text": "24-hour pharmacy please", "reason": "family",
                                                          "lat": GP[0], "lng": GP[1], "skip_duplicate_check": True})
    assert r.status_code == 201, r.text
    biz = make_user(role="business", business=BIZ)
    gp = _area_id(client, biz)

    g = client.get(f"{API}/reports/competitor-gap", params={"area_id": gp}, headers=biz)
    assert g.status_code == 200, g.text
    g = g.json()
    assert g["category"] == "pharmacy" and g["scope"] == "area"  # defaults to the business's own category
    assert g["metrics"]["supporters"] == 5 and g["metrics"]["competitors"] == 1 and g["metrics"]["per_outlet"] == 5.0
    assert g["metrics"]["city_avg_per_outlet"] == 5.0  # only Gol Pahadiya records a pharmacy in the test city
    assert g["verdict"]["label"] in VERDICTS and 0 <= g["verdict"]["score"] <= 100 and g["verdict"]["summary"]
    assert any(s["label"] == "Longer opening hours" for s in g["service_gaps"])
    assert {a["label"] for a in g["audience"]} == {"Daily need", "For families"}
    assert any(n["current"] for n in g["neighbours"]) and g["reasons"][0].startswith("5 verified residents")

    other = client.get(f"{API}/reports/competitor-gap", params={"area_id": _area_id(client, biz, "Thatipur"),
                                                                "category": "pharmacy"}, headers=biz).json()
    assert other["verdict"]["label"] == "No proven demand yet" and other["metrics"]["supporters"] == 0


def test_feasibility_status_checks_scenarios_and_assumptions(client, make_user):
    verified_demand(client, make_user, supporters=6)
    pid, _ = published_space(client, make_user)  # 79 sq m (850 sq ft) shop at ₹28,000/month
    biz = make_user(role="business", business=BIZ)

    r = client.post(f"{API}/reports/feasibility", json={"property_id": pid}, headers=biz)
    assert r.status_code == 200, r.text
    f = r.json()
    assert f["category"] == "pharmacy" and f["space"]["source"] == "listing" and f["space"]["price_amount"] == 28000
    assert f["status"]["label"] in {"Feasible", "Marginal", "Not feasible"} and 0 <= f["status"]["score"] <= 100
    keys = {c["key"] for c in f["checks"]}
    assert {"profit", "cushion", "rent", "payback", "downside", "budget", "size"} <= keys
    assert next(c for c in f["checks"] if c["key"] == "budget")["status"] == "good"  # ₹28,000 within ₹40,000
    revenues = [s["revenue"] for s in f["scenarios"]]
    assert [s["key"] for s in f["scenarios"]] == ["conservative", "expected", "optimistic"] and revenues == sorted(revenues)
    assert len(f["cash_curve"]) == 36 and f["cash_curve"][0]["cash"] < 0  # starts below zero by the setup cost
    assert f["setup"]["total"] == sum(f["setup"]["items"].values()) and f["setup"]["items"]["deposit"] == 6 * 28000
    exp = f["expected"]
    assert exp["profit"] == exp["revenue"] - sum(exp["costs"].values())
    assert f["breakeven"]["per_day"] and f["per_day"] is True and not f["customised"]

    tweaked = client.post(f"{API}/reports/feasibility", headers=biz, json={
        "property_id": pid, "assumptions": {"ticket": 200, "rent": 45000, "margin_pct": 15}}).json()
    assert tweaked["customised"] and tweaked["expected"]["costs"]["occupancy"] == 45000
    assert tweaked["expected"]["revenue"] < exp["revenue"] and tweaked["expected"]["profit"] < exp["profit"]
    assert next(a for a in tweaked["assumptions"] if a["key"] == "ticket")["value"] == 200

    typical = client.post(f"{API}/reports/feasibility", headers=biz,
                          json={"area_id": f["area"]["id"], "category": "pharmacy"}).json()
    assert typical["space"]["source"] == "typical" and typical["space"]["size_sqft"] > 0 and typical["space"]["price_amount"] > 0


def test_feasibility_models_a_sale_listing_with_a_loan(client, make_user):
    pid, _ = published_space(client, make_user, price_type="sale", price_amount=9_000_000)
    biz = make_user(role="business", business=BIZ)
    f = client.post(f"{API}/reports/feasibility", json={"property_id": pid, "category": "pharmacy"}, headers=biz).json()
    assert f["occupancy_label"] == "Loan EMI" and f["setup"]["items"]["down_payment"] == 1_800_000
    assert f["setup"]["items"]["deposit"] == 0 and 70000 < f["expected"]["costs"]["occupancy"] < 80000


def test_reports_are_for_businesses_and_need_a_scope(client, make_user):
    resident = make_user()
    gp = _area_id(client, resident)
    assert client.get(f"{API}/reports/competitor-gap", params={"area_id": gp}, headers=resident).status_code == 403
    biz = make_user(role="business", business=BIZ)
    assert client.get(f"{API}/reports/competitor-gap", headers=biz).status_code == 422
    owner = make_user(role="owner")
    draft = client.post(f"{API}/properties", json={"type": "shop", "size_value": 400, "lat": GP[0], "lng": GP[1]}, headers=owner).json()
    assert client.post(f"{API}/reports/feasibility", json={"property_id": draft["id"]}, headers=biz).status_code == 404

from fastapi.testclient import TestClient

from app.main import app

from .conftest import API, login


def _request(client, dest, channel="phone"):
    return client.post(f"{API}/auth/otp/request", json={"channel": channel, "destination": dest})


def test_phone_login_normalises_number_and_rotates_refresh_token(client):
    r = _request(client, "098765 43210")
    assert r.status_code == 200 and r.json()["destination"] == "+919876543210"
    code = r.json()["dev_code"]
    wrong = "000000" if code != "000000" else "111111"
    assert client.post(f"{API}/auth/otp/verify", json={"channel": "phone", "destination": "9876543210",
                                                       "code": wrong}).status_code == 400
    ok = client.post(f"{API}/auth/otp/verify", json={"channel": "phone", "destination": "+91 98765 43210", "code": code})
    assert ok.status_code == 200, ok.text
    assert ok.json()["is_new"] and ok.json()["user"]["roles"] == ["resident"]
    first = client.cookies.get("by_refresh")
    refreshed = client.post(f"{API}/auth/refresh")
    assert refreshed.status_code == 200 and refreshed.json()["access_token"]
    assert client.cookies.get("by_refresh") != first
    stale = TestClient(app)
    stale.cookies.set("by_refresh", first)
    assert stale.post(f"{API}/auth/refresh").status_code == 401
    me = client.get(f"{API}/me", headers={"Authorization": f"Bearer {refreshed.json()['access_token']}"})
    assert me.json()["phone"] == "+919876543210"


def test_invalid_destinations_are_rejected(client):
    assert _request(client, "12345").status_code == 422
    assert _request(client, "not-an-email", "email").status_code == 422


def test_code_locks_after_too_many_attempts(client):
    code = _request(client, "a@b.in", "email").json()["dev_code"]
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        client.post(f"{API}/auth/otp/verify", json={"channel": "email", "destination": "a@b.in", "code": wrong})
    r = client.post(f"{API}/auth/otp/verify", json={"channel": "email", "destination": "a@b.in", "code": code})
    assert r.status_code == 400 and "expired" in r.json()["detail"]


def test_code_requests_are_rate_limited(client):
    codes = [_request(client, "9811111111").status_code for _ in range(6)]
    assert codes[:5] == [200] * 5 and codes[5] == 429


def test_admin_allow_list_and_logout(client):
    h = login(client, "admin@test.in", "email")
    assert "admin" in client.get(f"{API}/me", headers=h).json()["roles"]
    assert client.post(f"{API}/auth/logout").status_code == 200
    assert client.post(f"{API}/auth/refresh").status_code == 401
    assert client.get(f"{API}/me").status_code == 401

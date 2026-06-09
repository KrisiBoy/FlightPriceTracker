"""Smoke test: FastAPI REST endpoints."""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from database import init_db
from main import app
from services.scheduler import stop_scheduler


def auth_headers(client: TestClient) -> dict[str, str]:
    """Register a test user and return Authorization headers."""
    response = client.post(
        "/api/auth/register",
        json={"email": "api-smoke@test.com", "password": "secretpass"},
    )
    assert response.status_code == 201
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def main() -> None:
    init_db()
    stop_scheduler()

    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        currencies = client.get("/api/currencies")
        assert currencies.status_code == 200
        body = currencies.json()
        assert "EUR" in body["currencies"]
        assert "HUF" in body["currencies"]
        assert body["default"] == "USD"

        headers = auth_headers(client)

        me = client.get("/api/auth/me", headers=headers)
        assert me.status_code == 200
        assert me.json()["email"] == "api-smoke@test.com"

        created = client.post(
            "/api/tracks",
            headers=headers,
            json={
                "departure_city": "JFK",
                "destination_city": "LHR",
                "departure_date": "2026-10-01",
                "return_date": "2026-10-08",
                "target_price": 450,
                "currency": "EUR",
            },
        )
        assert created.status_code == 201
        track = created.json()
        assert track["currency"] == "EUR"
        track_id = track["id"]

        listed = client.get("/api/tracks", headers=headers)
        assert listed.status_code == 200
        assert any(item["id"] == track_id for item in listed.json())

        history = client.get(f"/api/tracks/{track_id}/history", headers=headers)
        assert history.status_code == 200
        assert history.json() == []

        device = client.post(
            "/api/devices/register",
            headers=headers,
            json={"fcm_token": "smoke-test-token-xyz", "email": "api@test.com"},
        )
        assert device.status_code == 200
        assert device.json()["email"] == "api@test.com"

        updated = client.put(
            f"/api/tracks/{track_id}",
            headers=headers,
            json={
                "departure_city": "JFK",
                "destination_city": "CDG",
                "departure_date": "2026-10-01",
                "return_date": "2026-10-08",
                "target_price": 400,
                "currency": "EUR",
            },
        )
        assert updated.status_code == 200
        assert updated.json()["destination_city"] == "CDG"

        refresh = client.post("/api/refresh", headers=headers)
        assert refresh.status_code == 200
        refresh_body = refresh.json()
        assert refresh_body["routes_checked"] >= 1

        booking = client.get(f"/api/tracks/{track_id}/booking", headers=headers)
        assert booking.status_code == 200
        booking_body = booking.json()
        assert booking_body["url"].startswith("http")
        assert booking_body["currency"] == "EUR"

        deleted = client.delete(f"/api/tracks/{track_id}", headers=headers)
        assert deleted.status_code == 204

        missing = client.get(f"/api/tracks/{track_id}", headers=headers)
        assert missing.status_code == 404

        unauth = client.get("/api/tracks")
        assert unauth.status_code == 401

    print("API smoke test OK")


if __name__ == "__main__":
    main()

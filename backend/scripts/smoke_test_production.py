"""Smoke test against a live deployed Flight Price Tracker instance."""

from __future__ import annotations

import os
import sys
import time
import uuid
from datetime import date

import requests

PRODUCTION_URL = os.environ.get(
    "PRODUCTION_URL",
    "https://flightpricetracker-production.up.railway.app",
).rstrip("/")

REAL_SOURCES = {"skyscanner_rapidapi", "serpapi_google_flights"}
MOCK_PREFIX = "mock_"
TIMEOUT = 90


def api(method: str, path: str, **kwargs) -> requests.Response:
    url = f"{PRODUCTION_URL}{path}"
    return requests.request(method, url, timeout=TIMEOUT, **kwargs)


def main() -> None:
    print(f"Testing {PRODUCTION_URL}")

    health = api("GET", "/api/health")
    assert health.status_code == 200, health.text
    assert health.json()["status"] == "ok"
    print("  health OK")

    currencies = api("GET", "/api/currencies")
    assert currencies.status_code == 200
    body = currencies.json()
    assert "HUF" in body["currencies"]
    print("  currencies OK")

    stops = api("GET", "/api/stops")
    assert stops.status_code == 200
    print("  stops OK")

    email = f"prod-smoke-{uuid.uuid4().hex[:10]}@test.local"
    password = "smokepass99"
    register = api(
        "POST",
        "/api/auth/register",
        json={"email": email, "password": password},
    )
    assert register.status_code == 201, register.text
    token = register.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print(f"  register OK ({email})")

    me = api("GET", "/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["email"] == email
    print("  auth/me OK")

    created = api(
        "POST",
        "/api/tracks",
        headers=headers,
        json={
            "departure_city": "BUD",
            "destination_city": "LHR",
            "departure_date": "2026-09-15",
            "return_date": "2026-09-22",
            "target_price": 50000,
            "currency": "HUF",
            "stops": "any",
        },
    )
    assert created.status_code == 201, created.text
    track_id = created.json()["id"]
    print(f"  track created id={track_id}")

    refresh = api("POST", "/api/refresh", headers=headers)
    assert refresh.status_code == 200, refresh.text
    refresh_body = refresh.json()
    print(
        f"  refresh OK (checked={refresh_body['routes_checked']}, "
        f"errors={refresh_body['errors']})"
    )
    assert refresh_body["routes_checked"] >= 1
    assert refresh_body["errors"] == 0, "Price refresh failed — check Railway logs and API keys"

    track = api("GET", f"/api/tracks/{track_id}", headers=headers)
    assert track.status_code == 200, track.text
    track_body = track.json()
    source = track_body.get("source") or ""
    provider = track_body.get("provider_label") or ""
    price = track_body.get("current_price")
    print(f"  quote: {price} HUF via {provider} ({source})")

    assert price is not None and price > 0, "No price returned after refresh"
    if source.startswith(MOCK_PREFIX):
        print(
            "\nWARNING: Mock provider detected. On Railway set FLIGHT_API_MODE=live "
            "and add RAPIDAPI_KEY and/or SERPAPI_KEY, then redeploy.",
            file=sys.stderr,
        )
        sys.exit(2)
    assert source in REAL_SOURCES, f"Unexpected source: {source}"

    history = api("GET", f"/api/tracks/{track_id}/history", headers=headers)
    assert history.status_code == 200
    assert len(history.json()) >= 1
    print("  history OK")

    deleted = api("DELETE", f"/api/tracks/{track_id}", headers=headers)
    assert deleted.status_code == 204
    print("  cleanup OK")
    print("\nProduction smoke test passed (real API providers).")


if __name__ == "__main__":
    try:
        main()
    except requests.RequestException as exc:
        print(f"Request failed: {exc}", file=sys.stderr)
        sys.exit(1)

"""Smoke test: Skyscanner RapidAPI client (requires RAPIDAPI_KEY in env)."""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import get_settings
from services.flight_api import FlightSearchParams, SkyscannerRapidAPIClient


def main() -> None:
    settings = get_settings()
    if not settings.rapidapi_key:
        env_path = Path(__file__).resolve().parent.parent.parent / ".env"
        print("SKIP: RAPIDAPI_KEY not set")
        print(f"Add your RapidAPI key to: {env_path}")
        print("  RAPIDAPI_KEY=your-key-here")
        print("Copy the value from Railway → web service → Variables, or RapidAPI dashboard.")
        print("One-off test: $env:RAPIDAPI_KEY='your-key'; python scripts/smoke_test_skyscanner.py")
        return

    client = SkyscannerRapidAPIClient(api_key=settings.rapidapi_key)
    params = FlightSearchParams(
        departure_city="BUD",
        destination_city="LHR",
        departure_date=date(2026, 9, 15),
        return_date=date(2026, 9, 22),
        currency="HUF",
        stops="any",
    )
    quote = client.get_quote(params)
    assert quote.source == "skyscanner_rapidapi"
    assert quote.price > 0
    print(f"Skyscanner quote: {quote.price:,.0f} {quote.currency}")
    print("OK")


if __name__ == "__main__":
    main()

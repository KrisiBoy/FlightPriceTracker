"""Smoke test: mock flight API client and factory."""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.flight_api import FlightSearchParams, get_flight_api_client


def main() -> None:
    params = FlightSearchParams(
        departure_city="NYC",
        destination_city="LON",
        departure_date=date(2026, 8, 15),
        return_date=date(2026, 8, 22),
    )

    client = get_flight_api_client()
    quote1 = client.get_quote(params)
    quote2 = client.get_quote(params)

    assert quote1.price > 0
    assert quote2.price > 0
    assert quote1.source == "mock"
    assert quote1.currency == "USD"

    huf_params = FlightSearchParams(
        departure_city="BUD",
        destination_city="LON",
        departure_date=date(2026, 8, 15),
        return_date=date(2026, 8, 22),
        currency="HUF",
    )
    huf_quote = client.get_quote(huf_params)
    assert huf_quote.currency == "HUF"
    assert huf_quote.price >= 10_000

    print(f"Quote 1: ${quote1.price:.2f} ({quote1.source})")
    print(f"Quote 2: ${quote2.price:.2f} ({quote2.source})")
    print(f"HUF quote: {huf_quote.price:,.0f} Ft ({huf_quote.source})")
    print("OK")


if __name__ == "__main__":
    main()

"""Smoke test: multi-provider cheapest-quote selection."""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.flight_api import (
    FlightSearchParams,
    create_mock_provider_clients,
    fetch_best_quote,
    provider_label,
)


def main() -> None:
    params = FlightSearchParams(
        departure_city="BUD",
        destination_city="LHR",
        departure_date=date(2026, 9, 15),
        return_date=date(2026, 9, 22),
        currency="HUF",
        stops="direct",
    )
    clients = create_mock_provider_clients()
    best = fetch_best_quote(params, clients)

    assert len(clients) == 3
    assert best.stops_count == 0
    assert best.source in {"mock_skyscanner", "mock_google_flights", "mock_kiwi"}

    connecting = FlightSearchParams(
        departure_city="BUD",
        destination_city="LHR",
        departure_date=date(2026, 9, 15),
        currency="EUR",
        stops="connecting",
    )
    connecting_best = fetch_best_quote(connecting, clients)
    assert connecting_best.stops_count >= 1

    print(f"Providers checked: {len(clients)}")
    print(f"Cheapest: {best.price:,.0f} {best.currency} via {provider_label(best.source)}")
    print("OK")


if __name__ == "__main__":
    main()

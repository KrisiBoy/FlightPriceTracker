"""Smoke test: scheduler drop-detection logic."""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session, select

from auth import hash_password
from database import engine, init_db
from models import PriceHistory, TrackedRoute, User
from services.flight_api import FlightQuote, MockFlightAPIClient
from services.scheduler import check_route, get_lowest_historical_price, run_price_checks


class FixedPriceClient(MockFlightAPIClient):
    """Mock client that always returns a configured price."""

    def __init__(self, price: float, currency: str = "USD") -> None:
        super().__init__()
        self._price = price
        self._currency = currency

    def get_quote(self, params):  # type: ignore[override]
        return FlightQuote(
            price=self._price,
            currency=self._currency,
            source="mock_fixed",
            airline="TestAir",
        )


def main() -> None:
    init_db()

    with Session(engine) as session:
        session.exec(select(PriceHistory)).all()  # ensure imports work
        user = User(email="scheduler@test.com", password_hash=hash_password("secretpass"))
        session.add(user)
        session.commit()
        session.refresh(user)

        route = TrackedRoute(
            user_id=user.id,
            departure_city="JFK",
            destination_city="LHR",
            departure_date=date(2026, 9, 1),
            return_date=date(2026, 9, 10),
            target_price=500.0,
            active=True,
        )
        session.add(route)
        session.commit()
        session.refresh(route)
        assert route.id is not None

        session.add(PriceHistory(route_id=route.id, price=900.0))
        session.add(PriceHistory(route_id=route.id, price=850.0))
        session.commit()

        lowest = get_lowest_historical_price(session, route.id, route.currency)
        assert lowest == 850.0

        client = FixedPriceClient(price=420.0, currency="USD")
        result, alert = check_route(session, route, [client])
        session.commit()

        assert result.success
        assert result.drop_detected
        assert alert is not None
        assert alert.current_price == 420.0
        assert alert.previous_lowest == 850.0
        assert alert.currency == "USD"

        new_lowest = get_lowest_historical_price(session, route.id, route.currency)
        assert new_lowest == 420.0

    results, alerts = run_price_checks(clients=[FixedPriceClient(price=410.0)])
    assert len(results) >= 1
    print(f"Checked {len(results)} route(s), {len(alerts)} drop(s) in batch run")
    print("OK")


if __name__ == "__main__":
    main()

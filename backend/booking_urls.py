"""Resolve flight booking URLs for airline / aggregator sites."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional
from urllib.parse import quote

# Direct airline homepages used when no deeplink is available from the API.
AIRLINE_SITES: dict[str, str] = {
    "wizz air": "https://wizzair.com/en-gb",
    "ryanair": "https://www.ryanair.com",
    "lufthansa": "https://www.lufthansa.com",
    "british airways": "https://www.britishairways.com",
    "easyjet": "https://www.easyjet.com",
    "turkish airlines": "https://www.turkishairlines.com",
    "klm": "https://www.klm.com",
    "air france": "https://www.airfrance.com",
}


@dataclass(frozen=True)
class RouteBookingParams:
    """Minimal route data needed to build booking URLs."""

    departure_city: str
    destination_city: str
    departure_date: date
    return_date: Optional[date] = None
    currency: str = "USD"


def build_google_flights_search_url(params: RouteBookingParams) -> str:
    """Build a Google Flights search URL with route and dates pre-filled."""
    origin = params.departure_city.strip().upper()
    destination = params.destination_city.strip().upper()
    outbound = params.departure_date.isoformat()

    if params.return_date:
        query = (
            f"Flights from {origin} to {destination} on {outbound} "
            f"through {params.return_date.isoformat()}"
        )
    else:
        query = f"Flights from {origin} to {destination} on {outbound}"

    return f"https://www.google.com/travel/flights?q={quote(query)}"


def build_skyscanner_search_url(params: RouteBookingParams) -> str:
    """Build a Skyscanner search URL for the route."""
    origin = params.departure_city.strip().lower()
    destination = params.destination_city.strip().lower()
    outbound = params.departure_date.strftime("%y%m%d")
    currency = params.currency.lower()

    if params.return_date:
        inbound = params.return_date.strftime("%y%m%d")
        return (
            f"https://www.skyscanner.net/transport/flights/{origin}/{destination}/"
            f"{outbound}/{inbound}/?currency={currency}"
        )

    return (
        f"https://www.skyscanner.net/transport/flights/{origin}/{destination}/"
        f"{outbound}/?currency={currency}"
    )


def _resolve_serpapi_token(token: str) -> str:
    """Turn a SerpApi booking token into a Google Flights booking URL."""
    if token.startswith("http"):
        return token
    return f"https://www.google.com/travel/flights/booking?tfs={quote(token, safe='')}"


def airline_site_url(airline: Optional[str]) -> Optional[str]:
    """Return a known airline homepage URL, if the carrier is recognised."""
    if not airline:
        return None
    return AIRLINE_SITES.get(airline.strip().lower())


def resolve_booking_url(
    params: RouteBookingParams,
    *,
    booking_url: Optional[str] = None,
    airline: Optional[str] = None,
    source: str = "unknown",
) -> str:
    """Pick the best booking URL from quote metadata and route parameters."""
    if booking_url:
        if booking_url.startswith("http"):
            return booking_url
        return _resolve_serpapi_token(booking_url)

    airline_url = airline_site_url(airline)
    if airline_url and source == "mock":
        return airline_url

    if source == "skyscanner_rapidapi":
        return build_skyscanner_search_url(params)

    return build_google_flights_search_url(params)

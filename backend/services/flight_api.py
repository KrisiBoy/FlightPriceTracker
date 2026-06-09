"""Flight price API clients — mock, Skyscanner (RapidAPI), and Google Flights (SerpApi)."""

from __future__ import annotations

import hashlib
import logging
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Any, Optional

import requests
from requests import Response

from booking_urls import RouteBookingParams, airline_site_url, resolve_booking_url
from config import Settings, get_settings
from currencies import DEFAULT_CURRENCY, round_price, usd_factor
from stops import DEFAULT_STOPS, normalize_stops

logger = logging.getLogger(__name__)
DEFAULT_TIMEOUT_SECONDS = 30


class FlightAPIError(Exception):
    """Raised when a flight API request fails or returns unusable data."""


@dataclass(frozen=True)
class FlightSearchParams:
    """Parameters describing a flight route search."""

    departure_city: str
    destination_city: str
    departure_date: date
    return_date: Optional[date] = None
    currency: str = DEFAULT_CURRENCY
    stops: str = DEFAULT_STOPS
    seed_price: Optional[float] = None

    def route_key(self) -> str:
        """Return a stable identifier for caching and mock price seeds."""
        parts = [
            self.departure_city.strip().upper(),
            self.destination_city.strip().upper(),
            self.departure_date.isoformat(),
            self.return_date.isoformat() if self.return_date else "ONEWAY",
            self.currency.upper(),
            normalize_stops(self.stops),
        ]
        return "|".join(parts)


@dataclass(frozen=True)
class FlightQuote:
    """Normalized flight price quote returned by any client."""

    price: float
    currency: str = DEFAULT_CURRENCY
    source: str = "unknown"
    airline: Optional[str] = None
    booking_url: Optional[str] = None
    stops_count: int = 0


class FlightAPIClient(ABC):
    """Abstract interface for fetching flight prices."""

    @abstractmethod
    def get_quote(self, params: FlightSearchParams) -> FlightQuote:
        """Fetch the lowest available price for the given route."""

    def get_price(self, params: FlightSearchParams) -> float:
        """Convenience wrapper returning only the numeric price."""
        return self.get_quote(params).price


MOCK_AIRLINES: tuple[str, ...] = ("Wizz Air", "Ryanair", "Lufthansa", "British Airways", "easyJet")

PROVIDER_LABELS: dict[str, str] = {
    "mock_skyscanner": "Skyscanner",
    "mock_google_flights": "Google Flights",
    "mock_kiwi": "Kiwi.com",
    "skyscanner_rapidapi": "Skyscanner",
    "serpapi_google_flights": "Google Flights",
    "mock": "Mock",
}


def provider_label(source: str) -> str:
    """Return a display label for a provider source id."""
    return PROVIDER_LABELS.get(source, source.replace("_", " ").title())


@dataclass(frozen=True)
class MockProviderConfig:
    """Configuration for a simulated third-party provider."""

    source: str
    price_factor: float


class MockFlightAPIClient(FlightAPIClient):
    """Offline client that simulates realistic price fluctuations per route."""

    def __init__(self, volatility: float = 0.03) -> None:
        self._volatility = volatility
        self._last_prices: dict[str, float] = {}

    def _mock_airline(self, route_key: str) -> str:
        digest = hashlib.sha256(route_key.encode()).hexdigest()
        return MOCK_AIRLINES[int(digest[:2], 16) % len(MOCK_AIRLINES)]

    def _route_identity_key(self, params: FlightSearchParams) -> str:
        """Stable key for pricing — same route/currency always shares a baseline."""
        parts = [
            params.departure_city.strip().upper(),
            params.destination_city.strip().upper(),
            params.departure_date.isoformat(),
            params.return_date.isoformat() if params.return_date else "ONEWAY",
            params.currency.upper(),
            normalize_stops(params.stops),
        ]
        return "|".join(parts)

    def _resolve_stops_count(self, params: FlightSearchParams, route_key: str) -> int:
        """Return a stable stop count for the route based on the user's preference."""
        preference = normalize_stops(params.stops)
        if preference == "direct":
            return 0
        if preference == "connecting":
            digest = hashlib.sha256(f"{route_key}|stops".encode()).hexdigest()
            return 1 + int(digest[:1], 16) % 2
        digest = hashlib.sha256(f"{route_key}|any-stops".encode()).hexdigest()
        return int(digest[:1], 16) % 3

    def _stops_price_factor(self, stops_count: int) -> float:
        if stops_count == 0:
            return 1.18
        if stops_count == 1:
            return 0.92
        return 0.85

    def _base_price(self, params: FlightSearchParams) -> float:
        """Derive a stable baseline in the route's currency."""
        digest = hashlib.sha256(self._route_identity_key(params).encode()).hexdigest()
        seed = int(digest[:8], 16)
        rng = random.Random(seed)
        usd_baseline = rng.uniform(120.0, 850.0)
        return round_price(usd_baseline * usd_factor(params.currency), params.currency)

    def _minimum_price(self, currency: str) -> float:
        return round_price(49.0 * usd_factor(currency), currency)

    def get_quote(self, params: FlightSearchParams) -> FlightQuote:
        route_key = params.route_key()
        baseline = self._base_price(params)
        stops_count = self._resolve_stops_count(params, route_key)
        baseline = round_price(
            baseline * self._stops_price_factor(stops_count),
            params.currency,
        )

        if params.seed_price is not None:
            previous = params.seed_price
        else:
            previous = self._last_prices.get(route_key, baseline)

        delta = random.uniform(-self._volatility, self._volatility)
        raw = previous * (1 + delta)
        price = round_price(max(self._minimum_price(params.currency), raw), params.currency)
        self._last_prices[route_key] = price

        airline = self._mock_airline(route_key)
        route_params = RouteBookingParams(
            departure_city=params.departure_city,
            destination_city=params.destination_city,
            departure_date=params.departure_date,
            return_date=params.return_date,
            currency=params.currency,
        )
        booking_url = airline_site_url(airline) or resolve_booking_url(
            route_params, airline=airline, source="mock"
        )

        logger.debug("Mock quote for %s: %.2f %s", route_key, price, params.currency)
        return FlightQuote(
            price=price,
            currency=params.currency.upper(),
            source="mock",
            airline=airline,
            booking_url=booking_url,
            stops_count=stops_count,
        )


MOCK_PROVIDER_CONFIGS: tuple[MockProviderConfig, ...] = (
    MockProviderConfig("mock_skyscanner", 1.03),
    MockProviderConfig("mock_google_flights", 0.99),
    MockProviderConfig("mock_kiwi", 0.94),
)


class MockProviderFlightAPIClient(MockFlightAPIClient):
    """Mock client that simulates a specific aggregator/provider."""

    def __init__(self, config: MockProviderConfig, volatility: float = 0.03) -> None:
        super().__init__(volatility=volatility)
        self._config = config

    def get_quote(self, params: FlightSearchParams) -> FlightQuote:
        quote = super().get_quote(params)
        adjusted = round_price(quote.price * self._config.price_factor, quote.currency)
        return FlightQuote(
            price=adjusted,
            currency=quote.currency,
            source=self._config.source,
            airline=quote.airline,
            booking_url=quote.booking_url,
            stops_count=quote.stops_count,
        )


class SkyscannerRapidAPIClient(FlightAPIClient):
    """Skyscanner browse-quotes client via RapidAPI."""

    HOST = "skyscanner-skyscanner-flights-v1.p.rapidapi.com"
    BASE_URL = f"https://{HOST}/apiservices/browsequotes/v1.0"

    def __init__(self, api_key: str, country: str = "US", locale: str = "en-US") -> None:
        if not api_key:
            raise FlightAPIError("RAPIDAPI_KEY is required for Skyscanner client.")
        self._api_key = api_key
        self._country = country
        self._currency = DEFAULT_CURRENCY
        self._locale = locale

    def _headers(self) -> dict[str, str]:
        return {
            "X-RapidAPI-Key": self._api_key,
            "X-RapidAPI-Host": self.HOST,
        }

    def _request(self, path: str) -> Response:
        url = f"{self.BASE_URL}/{path}"
        try:
            response = requests.get(
                url,
                headers=self._headers(),
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            raise FlightAPIError(f"Skyscanner request failed: {exc}") from exc

    def get_quote(self, params: FlightSearchParams) -> FlightQuote:
        origin = params.departure_city.strip().upper()
        destination = params.destination_city.strip().upper()
        outbound = params.departure_date.strftime("%Y-%m-%d")
        inbound = params.return_date.strftime("%Y-%m-%d") if params.return_date else ""

        currency = params.currency.upper()
        path = (
            f"{self._country}/{currency}/{self._locale}/"
            f"{origin}/{destination}/{outbound}/{inbound}"
        )
        response = self._request(path)
        payload = response.json()
        carriers = payload.get("Carriers", [])
        quotes = payload.get("Quotes", [])
        price, stops_count = self._extract_lowest_price(payload, params.stops)
        airline = self._extract_airline(quotes, carriers)

        route_params = RouteBookingParams(
            departure_city=params.departure_city,
            destination_city=params.destination_city,
            departure_date=params.departure_date,
            return_date=params.return_date,
            currency=params.currency,
        )
        booking_url = resolve_booking_url(
            route_params, airline=airline, source="skyscanner_rapidapi"
        )
        return FlightQuote(
            price=price,
            currency=currency,
            source="skyscanner_rapidapi",
            airline=airline,
            booking_url=booking_url,
            stops_count=stops_count,
        )

    @staticmethod
    def _quote_matches_stops(quote: dict[str, Any], stops: str) -> bool:
        preference = normalize_stops(stops)
        if preference == "any":
            return True
        is_direct = bool(quote.get("Direct"))
        if preference == "direct":
            return is_direct
        return not is_direct

    @staticmethod
    def _quote_stops_count(quote: dict[str, Any]) -> int:
        return 0 if quote.get("Direct") else 1

    def _extract_lowest_price(self, payload: dict[str, Any], stops: str) -> tuple[float, int]:
        quotes = payload.get("Quotes", [])
        if not quotes:
            raise FlightAPIError("Skyscanner returned no quotes for this route.")

        filtered = [quote for quote in quotes if self._quote_matches_stops(quote, stops)]
        if not filtered:
            raise FlightAPIError(
                f"Skyscanner returned no {normalize_stops(stops)} quotes for this route."
            )

        best = min(filtered, key=lambda quote: float(quote.get("MinPrice", float("inf"))))
        price = best.get("MinPrice")
        if price is None:
            raise FlightAPIError("Skyscanner quotes did not include prices.")

        return float(price), self._quote_stops_count(best)

    @staticmethod
    def _extract_airline(
        quotes: list[dict[str, Any]],
        carriers: list[dict[str, Any]],
    ) -> Optional[str]:
        if not quotes:
            return None
        outbound_leg = quotes[0].get("OutboundLeg", {})
        carrier_ids = outbound_leg.get("CarrierIds") or []
        if not carrier_ids:
            return None
        carrier_id = carrier_ids[0]
        for carrier in carriers:
            if carrier.get("Id") == carrier_id:
                return carrier.get("Name")
        return None


class SerpApiGoogleFlightsClient(FlightAPIClient):
    """Google Flights client via SerpApi."""

    BASE_URL = "https://serpapi.com/search.json"

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise FlightAPIError("SERPAPI_KEY is required for SerpApi client.")
        self._api_key = api_key

    def _request(self, params: FlightSearchParams) -> dict[str, Any]:
        query: dict[str, str | int] = {
            "engine": "google_flights",
            "api_key": self._api_key,
            "departure_id": params.departure_city.strip().upper(),
            "arrival_id": params.destination_city.strip().upper(),
            "outbound_date": params.departure_date.isoformat(),
            "currency": params.currency.upper(),
        }
        if params.return_date:
            query["return_date"] = params.return_date.isoformat()
            query["type"] = 1  # round trip
        else:
            query["type"] = 2  # one way

        preference = normalize_stops(params.stops)
        if preference == "direct":
            query["stops"] = 1

        try:
            response = requests.get(self.BASE_URL, params=query, timeout=DEFAULT_TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            raise FlightAPIError(f"SerpApi request failed: {exc}") from exc

    def get_quote(self, params: FlightSearchParams) -> FlightQuote:
        payload = self._request(params)
        price, airline, booking_url, stops_count = self._extract_best_offer(
            payload,
            params.stops,
        )

        return FlightQuote(
            price=price,
            currency=params.currency.upper(),
            source="serpapi_google_flights",
            airline=airline,
            booking_url=booking_url,
            stops_count=stops_count,
        )

    @staticmethod
    def _offer_stops_count(offer: dict[str, Any]) -> int:
        flights = offer.get("flights") or []
        if len(flights) <= 1:
            return 0
        return max(len(flights) - 1, 1)

    @staticmethod
    def _offer_matches_stops(offer: dict[str, Any], stops: str) -> bool:
        preference = normalize_stops(stops)
        if preference == "any":
            return True
        stops_count = SerpApiGoogleFlightsClient._offer_stops_count(offer)
        if preference == "direct":
            return stops_count == 0
        return stops_count >= 1

    @staticmethod
    def _extract_best_offer(
        payload: dict[str, Any],
        stops: str,
    ) -> tuple[float, Optional[str], Optional[str], int]:
        if payload.get("error"):
            raise FlightAPIError(str(payload["error"]))

        offers = (payload.get("best_flights") or []) + (payload.get("other_flights") or [])
        if not offers:
            raise FlightAPIError("SerpApi returned no flight offers for this route.")

        filtered = [offer for offer in offers if SerpApiGoogleFlightsClient._offer_matches_stops(offer, stops)]
        if not filtered:
            raise FlightAPIError(
                f"SerpApi returned no {normalize_stops(stops)} offers for this route."
            )

        def offer_price(offer: dict[str, Any]) -> float:
            price_block = offer.get("price")
            if isinstance(price_block, dict):
                value = price_block.get("raw") or price_block.get("extracted")
            else:
                value = price_block
            return float(value) if value is not None else float("inf")

        offer = min(filtered, key=offer_price)
        price_block = offer.get("price")
        if isinstance(price_block, dict):
            price = price_block.get("raw") or price_block.get("extracted")
        else:
            price = price_block

        if price is None:
            raise FlightAPIError("SerpApi offer did not include a price.")

        airline = None
        flights = offer.get("flights") or []
        if flights:
            airline = flights[0].get("airline")

        booking_url = offer.get("booking_token") or offer.get("departure_token")
        return float(price), airline, booking_url, SerpApiGoogleFlightsClient._offer_stops_count(offer)


def quote_with_resolved_booking_url(
    quote: FlightQuote,
    params: FlightSearchParams,
) -> FlightQuote:
    """Return a quote whose booking_url is a fully resolved HTTP link."""
    route_params = RouteBookingParams(
        departure_city=params.departure_city,
        destination_city=params.destination_city,
        departure_date=params.departure_date,
        return_date=params.return_date,
        currency=params.currency,
    )
    resolved = resolve_booking_url(
        route_params,
        booking_url=quote.booking_url,
        airline=quote.airline,
        source=quote.source,
    )
    return FlightQuote(
        price=quote.price,
        currency=quote.currency,
        source=quote.source,
        airline=quote.airline,
        booking_url=resolved,
        stops_count=quote.stops_count,
    )


def create_mock_provider_clients() -> list[FlightAPIClient]:
    """Return simulated provider clients for offline multi-provider checks."""
    return [MockProviderFlightAPIClient(config) for config in MOCK_PROVIDER_CONFIGS]


def get_available_flight_clients(settings: Optional[Settings] = None) -> list[FlightAPIClient]:
    """Return every configured provider client for a route price check."""
    settings = settings or get_settings()
    clients: list[FlightAPIClient] = []

    if settings.rapidapi_key:
        clients.append(SkyscannerRapidAPIClient(api_key=settings.rapidapi_key))
    if settings.serpapi_key:
        clients.append(SerpApiGoogleFlightsClient(api_key=settings.serpapi_key))

    if settings.flight_api_mode.strip().lower() == "mock" or not clients:
        clients = create_mock_provider_clients()

    return clients


def fetch_best_quote(
    params: FlightSearchParams,
    clients: Optional[list[FlightAPIClient]] = None,
) -> FlightQuote:
    """Query all providers and return the cheapest matching quote."""
    clients = clients or get_available_flight_clients()
    quotes: list[FlightQuote] = []
    errors: list[str] = []

    for client in clients:
        try:
            quote = quote_with_resolved_booking_url(client.get_quote(params), params)
            quotes.append(quote)
            logger.debug(
                "Provider %s returned %.2f %s (%d stops)",
                quote.source,
                quote.price,
                quote.currency,
                quote.stops_count,
            )
        except FlightAPIError as exc:
            errors.append(str(exc))
            logger.warning("Provider quote failed: %s", exc)

    if not quotes:
        detail = "; ".join(errors) if errors else "No providers configured."
        raise FlightAPIError(f"No quotes available from any provider. {detail}")

    best = min(quotes, key=lambda quote: quote.price)
    logger.info(
        "Best quote for %s → %s: %.2f %s via %s",
        params.departure_city,
        params.destination_city,
        best.price,
        best.currency,
        provider_label(best.source),
    )
    return best


def get_flight_api_client(settings: Optional[Settings] = None) -> FlightAPIClient:
    """Return the configured flight API client based on FLIGHT_API_MODE."""
    settings = settings or get_settings()
    mode = settings.flight_api_mode.strip().lower()

    if mode == "mock":
        return MockFlightAPIClient()

    if mode in {"rapidapi", "skyscanner"}:
        return SkyscannerRapidAPIClient(api_key=settings.rapidapi_key)

    if mode in {"serpapi", "google", "google_flights"}:
        return SerpApiGoogleFlightsClient(api_key=settings.serpapi_key)

    raise FlightAPIError(
        f"Unsupported FLIGHT_API_MODE '{settings.flight_api_mode}'. "
        "Use mock, rapidapi, or serpapi."
    )


class AggregatorFlightAPIClient(FlightAPIClient):
    """Client wrapper that picks the cheapest quote across providers."""

    def __init__(self, clients: Optional[list[FlightAPIClient]] = None) -> None:
        self._clients = clients

    def get_quote(self, params: FlightSearchParams) -> FlightQuote:
        return fetch_best_quote(params, self._clients or get_available_flight_clients())

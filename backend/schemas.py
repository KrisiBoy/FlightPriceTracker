"""Pydantic schemas for REST API request and response bodies."""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from currencies import DEFAULT_CURRENCY, normalize_currency
from stops import DEFAULT_STOPS, normalize_stops


class UserRegister(BaseModel):
    """Payload for creating a new account."""

    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class UserLogin(BaseModel):
    """Payload for signing in."""

    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class TokenRead(BaseModel):
    """JWT access token response."""

    access_token: str
    token_type: str = "bearer"


class UserRead(BaseModel):
    """Public user profile."""

    id: int
    email: str
    alert_email: Optional[str] = None
    email_notifications_enabled: bool = True
    push_notifications_enabled: bool = True
    created_at: datetime

    model_config = {"from_attributes": True}


class NotificationPreferencesUpdate(BaseModel):
    """Update notification channel preferences for the current user."""

    email_notifications_enabled: Optional[bool] = None
    push_notifications_enabled: Optional[bool] = None
    alert_email: Optional[str] = Field(default=None, max_length=255)

    @field_validator("alert_email")
    @classmethod
    def normalize_alert_email(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip().lower()
        return normalized or None


class TrackCreate(BaseModel):
    """Payload for creating a tracked route."""

    departure_city: str = Field(min_length=2, max_length=100)
    destination_city: str = Field(min_length=2, max_length=100)
    departure_date: date
    return_date: Optional[date] = None
    target_price: Optional[float] = Field(default=None, ge=0)
    currency: str = Field(default=DEFAULT_CURRENCY, max_length=3)
    stops: str = Field(default=DEFAULT_STOPS, max_length=20)

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        return normalize_currency(value)

    @field_validator("stops")
    @classmethod
    def validate_stops(cls, value: str) -> str:
        return normalize_stops(value)

    @field_validator("destination_city", "departure_city")
    @classmethod
    def strip_cities(cls, value: str) -> str:
        return value.strip()


class TrackRead(BaseModel):
    """Tracked route with summary price stats."""

    id: int
    departure_city: str
    destination_city: str
    departure_date: date
    return_date: Optional[date]
    target_price: Optional[float]
    currency: str
    stops: str
    active: bool
    created_at: datetime
    current_price: Optional[float] = None
    lowest_price: Optional[float] = None
    airline: Optional[str] = None
    source: Optional[str] = None
    provider_label: Optional[str] = None
    stops_count: Optional[int] = None
    booking_url: Optional[str] = None

    model_config = {"from_attributes": True}


class BookingLinkRead(BaseModel):
    """Live booking link for opening the airline / aggregator site."""

    track_id: int
    url: str
    airline: Optional[str] = None
    price: Optional[float] = None
    currency: str


class PriceHistoryRead(BaseModel):
    """A single historical price observation."""

    id: int
    route_id: int
    price: float
    currency: str
    checked_at: datetime

    model_config = {"from_attributes": True}


class DeviceRegister(BaseModel):
    """Payload for registering a device for notifications."""

    fcm_token: str = Field(min_length=10, max_length=512)
    email: Optional[str] = Field(default=None, max_length=255)


class DeviceRead(BaseModel):
    """Registered device response."""

    id: int
    fcm_token: str
    email: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class AirportRead(BaseModel):
    """Airport suggestion for autocomplete."""

    iata: str
    name: str
    city: str
    country: str


class CurrencyList(BaseModel):
    """Supported currency codes."""

    currencies: list[str]
    default: str = DEFAULT_CURRENCY


class StopsList(BaseModel):
    """Supported stop preferences for route searches."""

    options: list[str]
    default: str = DEFAULT_STOPS
    labels: dict[str, str]


class RefreshResult(BaseModel):
    """Summary of an on-demand price check run."""

    routes_checked: int
    drops_detected: int
    errors: int

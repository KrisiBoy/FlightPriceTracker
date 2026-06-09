"""SQLModel database models for the Flight Price Tracker."""

from datetime import date, datetime, timezone
from typing import List, Optional

from currencies import DEFAULT_CURRENCY
from stops import DEFAULT_STOPS
from sqlalchemy import Index
from sqlmodel import Field, Relationship, SQLModel


def utc_now() -> datetime:
    """Return the current UTC datetime."""
    return datetime.now(timezone.utc)


class User(SQLModel, table=True):
    """Registered application user."""

    __tablename__ = "user"

    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True, max_length=255)
    password_hash: str = Field(max_length=255)
    alert_email: Optional[str] = Field(default=None, max_length=255)
    email_notifications_enabled: bool = Field(default=True)
    push_notifications_enabled: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utc_now)


class TrackedRoute(SQLModel, table=True):
    """A flight route being monitored for price changes."""

    __tablename__ = "tracked_route"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)
    departure_city: str = Field(index=True, max_length=100)
    destination_city: str = Field(index=True, max_length=100)
    departure_date: date
    return_date: Optional[date] = Field(default=None)
    target_price: Optional[float] = Field(default=None, ge=0)
    currency: str = Field(default=DEFAULT_CURRENCY, max_length=3, index=True)
    stops: str = Field(default=DEFAULT_STOPS, max_length=20, index=True)
    active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utc_now)

    price_history: List["PriceHistory"] = Relationship(
        back_populates="route",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class PriceHistory(SQLModel, table=True):
    """A single price observation for a tracked route."""

    __tablename__ = "price_history"
    __table_args__ = (
        Index("ix_price_history_route_checked", "route_id", "checked_at"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    route_id: int = Field(foreign_key="tracked_route.id", index=True)
    price: float = Field(ge=0)
    currency: str = Field(default=DEFAULT_CURRENCY, max_length=3)
    airline: Optional[str] = Field(default=None, max_length=100)
    source: Optional[str] = Field(default=None, max_length=50)
    stops_count: Optional[int] = Field(default=None, ge=0)
    booking_url: Optional[str] = Field(default=None, max_length=2048)
    checked_at: datetime = Field(default_factory=utc_now, index=True)

    route: Optional[TrackedRoute] = Relationship(back_populates="price_history")


class UserDevice(SQLModel, table=True):
    """A registered mobile device for push notifications."""

    __tablename__ = "user_device"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)
    fcm_token: str = Field(unique=True, index=True, max_length=512)
    email: Optional[str] = Field(default=None, max_length=255)
    created_at: datetime = Field(default_factory=utc_now)

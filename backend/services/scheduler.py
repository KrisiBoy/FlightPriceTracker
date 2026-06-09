"""Background price-check scheduler and drop-detection engine."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlmodel import Session, select

from config import Settings, get_settings
from database import session_scope
from models import PriceHistory, TrackedRoute, utc_now
from services.flight_api import (
    FlightAPIClient,
    FlightAPIError,
    FlightSearchParams,
    fetch_best_quote,
    get_available_flight_clients,
)

logger = logging.getLogger(__name__)

_scheduler: Optional[BackgroundScheduler] = None


@dataclass(frozen=True)
class PriceDropAlert:
    """Payload prepared when a price falls below historical low.

    ``currency`` reflects the tracked route's configured currency.
    """

    route_id: int
    user_id: Optional[int]
    departure_city: str
    destination_city: str
    departure_date: date
    return_date: Optional[date]
    previous_lowest: float
    current_price: float
    currency: str
    target_price: Optional[float] = None
    airline: Optional[str] = None


@dataclass
class RouteCheckResult:
    """Outcome of a single route price check."""

    route_id: int
    success: bool
    current_price: Optional[float] = None
    currency: Optional[str] = None
    drop_detected: bool = False
    error: Optional[str] = None


def get_lowest_historical_price(
    session: Session,
    route_id: int,
    currency: str,
) -> Optional[float]:
    """Return the minimum recorded price for a route in the given currency."""
    statement = (
        select(PriceHistory.price)
        .where(PriceHistory.route_id == route_id)
        .where(PriceHistory.currency == currency)
        .order_by(PriceHistory.price.asc())
        .limit(1)
    )
    return session.exec(statement).first()


def get_latest_historical_price(
    session: Session,
    route_id: int,
    currency: str,
) -> Optional[float]:
    """Return the most recent price for a route in the given currency."""
    statement = (
        select(PriceHistory.price)
        .where(PriceHistory.route_id == route_id)
        .where(PriceHistory.currency == currency)
        .order_by(PriceHistory.checked_at.desc())
        .limit(1)
    )
    return session.exec(statement).first()


def _build_search_params(
    route: TrackedRoute,
    *,
    seed_price: Optional[float] = None,
) -> FlightSearchParams:
    return FlightSearchParams(
        departure_city=route.departure_city,
        destination_city=route.destination_city,
        departure_date=route.departure_date,
        return_date=route.return_date,
        currency=route.currency,
        stops=route.stops,
        seed_price=seed_price,
    )


def check_route(
    session: Session,
    route: TrackedRoute,
    clients: Optional[list[FlightAPIClient]] = None,
) -> tuple[RouteCheckResult, Optional[PriceDropAlert]]:
    """Fetch a quote, persist history, and detect price drops for one route."""
    if not route.active or route.id is None:
        return RouteCheckResult(route_id=route.id or 0, success=False, error="inactive"), None

    try:
        seed_price = get_latest_historical_price(session, route.id, route.currency)
        search = _build_search_params(route, seed_price=seed_price)
        quote = fetch_best_quote(search, clients)
    except FlightAPIError as exc:
        logger.error("Price check failed for route %s: %s", route.id, exc)
        return RouteCheckResult(route_id=route.id, success=False, error=str(exc)), None

    previous_lowest = get_lowest_historical_price(session, route.id, route.currency)
    session.add(
        PriceHistory(
            route_id=route.id,
            price=quote.price,
            currency=quote.currency,
            airline=quote.airline,
            source=quote.source,
            stops_count=quote.stops_count,
            booking_url=quote.booking_url,
            checked_at=utc_now(),
        )
    )
    session.flush()

    drop_alert: Optional[PriceDropAlert] = None
    drop_detected = previous_lowest is not None and quote.price < previous_lowest

    if drop_detected and previous_lowest is not None:
        drop_alert = PriceDropAlert(
            route_id=route.id,
            user_id=route.user_id,
            departure_city=route.departure_city,
            destination_city=route.destination_city,
            departure_date=route.departure_date,
            return_date=route.return_date,
            previous_lowest=previous_lowest,
            current_price=quote.price,
            currency=quote.currency,
            target_price=route.target_price,
            airline=quote.airline,
        )
        logger.info(
            "Price drop on route %s (%s → %s): %.2f %s → %.2f %s",
            route.id,
            route.departure_city,
            route.destination_city,
            previous_lowest,
            quote.currency,
            quote.price,
            quote.currency,
        )

    return RouteCheckResult(
        route_id=route.id,
        success=True,
        current_price=quote.price,
        currency=quote.currency,
        drop_detected=drop_detected,
    ), drop_alert


def run_price_checks(
    clients: Optional[list[FlightAPIClient]] = None,
    dispatch_notifications: bool = False,
    user_id: Optional[int] = None,
) -> tuple[list[RouteCheckResult], list[PriceDropAlert]]:
    """Check active routes and return results plus drop alerts."""
    clients = clients or get_available_flight_clients()
    results: list[RouteCheckResult] = []
    alerts: list[PriceDropAlert] = []

    with session_scope() as session:
        statement = select(TrackedRoute).where(TrackedRoute.active.is_(True))
        if user_id is not None:
            statement = statement.where(TrackedRoute.user_id == user_id)
        routes = session.exec(statement).all()

        for route in routes:
            result, alert = check_route(session, route, clients)
            results.append(result)
            if alert:
                alerts.append(alert)

    logger.info(
        "Price check complete: %d routes, %d drops",
        len(results),
        len(alerts),
    )

    if dispatch_notifications and alerts:
        from services.notification import dispatch_drop_alerts

        dispatch_drop_alerts(alerts)

    return results, alerts


def scheduled_price_check_job() -> None:
    """APScheduler entry point: check prices and notify on drops."""
    run_price_checks(dispatch_notifications=True)


def _parse_scheduler_hours(hours_csv: str) -> str:
    """Validate and normalize comma-separated UTC hour values."""
    hours = [part.strip() for part in hours_csv.split(",") if part.strip()]
    if not hours:
        raise ValueError("scheduler_hours must contain at least one hour.")

    for hour in hours:
        value = int(hour)
        if value < 0 or value > 23:
            raise ValueError(f"Invalid scheduler hour: {hour}")

    return ",".join(str(int(h)) for h in hours)


def start_scheduler(settings: Optional[Settings] = None) -> BackgroundScheduler:
    """Start the background scheduler (idempotent)."""
    global _scheduler
    settings = settings or get_settings()

    if _scheduler and _scheduler.running:
        return _scheduler

    if not settings.scheduler_enabled:
        logger.info("Scheduler disabled via SCHEDULER_ENABLED=false")
        return BackgroundScheduler()

    hours = _parse_scheduler_hours(settings.scheduler_hours)
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        scheduled_price_check_job,
        trigger=CronTrigger(hour=hours, minute=0),
        id="flight_price_check",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    _scheduler = scheduler
    logger.info("Scheduler started — price checks at UTC hours: %s", hours)
    return scheduler


def stop_scheduler() -> None:
    """Shut down the background scheduler if running."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
    _scheduler = None


def get_scheduler() -> Optional[BackgroundScheduler]:
    """Return the active scheduler instance, if any."""
    return _scheduler

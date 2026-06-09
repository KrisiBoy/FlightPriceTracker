"""FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Annotated, Optional

from fastapi import Depends, FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session, select

from airports import search_airports
from auth import (
    CurrentUser,
    create_access_token,
    get_user_by_email,
    hash_password,
    verify_password,
)
from config import PROJECT_ROOT, get_settings
from currencies import DEFAULT_CURRENCY, SUPPORTED_CURRENCIES
from database import get_session, init_db
from models import PriceHistory, TrackedRoute, User, UserDevice
from schemas import (
    AirportRead,
    BookingLinkRead,
    CurrencyList,
    DeviceRead,
    DeviceRegister,
    PriceHistoryRead,
    RefreshResult,
    StopsList,
    TokenRead,
    TrackCreate,
    TrackRead,
    UserLogin,
    UserRead,
    UserRegister,
)
from stops import DEFAULT_STOPS, STOPS_LABELS, SUPPORTED_STOPS
from services.flight_api import (
    FlightAPIError,
    fetch_best_quote,
    get_available_flight_clients,
    provider_label,
)
from services.scheduler import _build_search_params, run_price_checks, start_scheduler, stop_scheduler

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialize database and background scheduler on startup."""
    logging.basicConfig(level=logging.INFO)
    init_db()
    start_scheduler(settings)
    yield
    stop_scheduler()


app = FastAPI(
    title="Flight Price Tracker",
    version="1.0.0",
    lifespan=lifespan,
)

_origins = settings.cors_origins.strip()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if _origins == "*" else [o.strip() for o in _origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SessionDep = Annotated[Session, Depends(get_session)]


def _latest_history(session: Session, route_id: int) -> Optional[PriceHistory]:
    """Return the most recent price history row for a route."""
    return session.exec(
        select(PriceHistory)
        .where(PriceHistory.route_id == route_id)
        .order_by(PriceHistory.checked_at.desc())
        .limit(1)
    ).first()


def _route_stats(
    session: Session,
    route_id: int,
    currency: str,
) -> tuple[Optional[float], Optional[float]]:
    """Return (current_price, lowest_price) for a route in its currency."""
    history = session.exec(
        select(PriceHistory)
        .where(PriceHistory.route_id == route_id)
        .where(PriceHistory.currency == currency)
        .order_by(PriceHistory.checked_at.desc())
    ).all()
    if not history:
        return None, None
    prices = [row.price for row in history]
    return history[0].price, min(prices)


def _get_user_route(session: Session, track_id: int, user: User) -> TrackedRoute:
    """Return a route owned by the user or raise 404."""
    route = session.get(TrackedRoute, track_id)
    if not route or route.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Track not found")
    return route


def _to_track_read(session: Session, route: TrackedRoute) -> TrackRead:
    current, lowest = _route_stats(session, route.id, route.currency)  # type: ignore[arg-type]
    latest = _latest_history(session, route.id)  # type: ignore[arg-type]
    return TrackRead(
        id=route.id,  # type: ignore[arg-type]
        departure_city=route.departure_city,
        destination_city=route.destination_city,
        departure_date=route.departure_date,
        return_date=route.return_date,
        target_price=route.target_price,
        currency=route.currency,
        stops=route.stops,
        active=route.active,
        created_at=route.created_at,
        current_price=current,
        lowest_price=lowest,
        airline=latest.airline if latest else None,
        source=latest.source if latest else None,
        provider_label=provider_label(latest.source) if latest and latest.source else None,
        stops_count=latest.stops_count if latest else None,
        booking_url=latest.booking_url if latest else None,
    )


@app.get("/api/health")
def health_check() -> dict[str, str]:
    """Simple health probe."""
    return {"status": "ok"}


@app.get("/api/currencies", response_model=CurrencyList)
def list_currencies() -> CurrencyList:
    """Return supported currency codes for the frontend selector."""
    return CurrencyList(currencies=list(SUPPORTED_CURRENCIES), default=DEFAULT_CURRENCY)


@app.get("/api/stops", response_model=StopsList)
def list_stops() -> StopsList:
    """Return supported stop preferences for the frontend selector."""
    return StopsList(
        options=list(SUPPORTED_STOPS),
        default=DEFAULT_STOPS,
        labels=STOPS_LABELS,
    )


@app.post("/api/auth/register", response_model=TokenRead, status_code=status.HTTP_201_CREATED)
def register_user(payload: UserRegister, session: SessionDep) -> TokenRead:
    """Create a new user account."""
    if get_user_by_email(session, payload.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user = User(email=payload.email, password_hash=hash_password(payload.password))
    session.add(user)
    session.commit()
    session.refresh(user)
    token = create_access_token(user.id)  # type: ignore[arg-type]
    return TokenRead(access_token=token)


@app.post("/api/auth/login", response_model=TokenRead)
def login_user(payload: UserLogin, session: SessionDep) -> TokenRead:
    """Authenticate and return a JWT."""
    user = get_user_by_email(session, payload.email)
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    token = create_access_token(user.id)  # type: ignore[arg-type]
    return TokenRead(access_token=token)


@app.get("/api/auth/me", response_model=UserRead)
def get_me(current_user: CurrentUser) -> UserRead:
    """Return the authenticated user's profile."""
    return UserRead.model_validate(current_user)


@app.get("/api/airports/search", response_model=list[AirportRead])
def airport_search(q: str = "", limit: int = 8) -> list[AirportRead]:
    """Search airports by IATA code, city, country, or name."""
    capped = min(max(limit, 1), 20)
    return [
        AirportRead(iata=row.iata, name=row.name, city=row.city, country=row.country)
        for row in search_airports(q, limit=capped)
    ]


@app.post("/api/tracks", response_model=TrackRead, status_code=status.HTTP_201_CREATED)
def create_track(
    payload: TrackCreate,
    session: SessionDep,
    current_user: CurrentUser,
) -> TrackRead:
    """Create a new tracked flight route."""
    route = TrackedRoute(
        user_id=current_user.id,
        departure_city=payload.departure_city,
        destination_city=payload.destination_city,
        departure_date=payload.departure_date,
        return_date=payload.return_date,
        target_price=payload.target_price,
        currency=payload.currency,
        stops=payload.stops,
    )
    session.add(route)
    session.commit()
    session.refresh(route)
    return _to_track_read(session, route)


@app.get("/api/tracks", response_model=list[TrackRead])
def list_tracks(session: SessionDep, current_user: CurrentUser) -> list[TrackRead]:
    """List tracked routes for the authenticated user."""
    routes = session.exec(
        select(TrackedRoute)
        .where(TrackedRoute.user_id == current_user.id)
        .order_by(TrackedRoute.created_at.desc())
    ).all()
    return [_to_track_read(session, route) for route in routes]


@app.post("/api/refresh", response_model=RefreshResult)
def refresh_tracks_now(current_user: CurrentUser) -> RefreshResult:
    """Check the current user's active routes and dispatch drop notifications."""
    results, alerts = run_price_checks(
        dispatch_notifications=True,
        user_id=current_user.id,
    )
    errors = sum(1 for result in results if not result.success)
    return RefreshResult(
        routes_checked=len(results),
        drops_detected=len(alerts),
        errors=errors,
    )


@app.get("/api/tracks/{track_id}", response_model=TrackRead)
def get_track(track_id: int, session: SessionDep, current_user: CurrentUser) -> TrackRead:
    """Return a single tracked route."""
    route = _get_user_route(session, track_id, current_user)
    return _to_track_read(session, route)


@app.put("/api/tracks/{track_id}", response_model=TrackRead)
def update_track(
    track_id: int,
    payload: TrackCreate,
    session: SessionDep,
    current_user: CurrentUser,
) -> TrackRead:
    """Update an existing tracked route."""
    route = _get_user_route(session, track_id, current_user)

    currency_changed = route.currency != payload.currency
    stops_changed = route.stops != payload.stops

    route.departure_city = payload.departure_city
    route.destination_city = payload.destination_city
    route.departure_date = payload.departure_date
    route.return_date = payload.return_date
    route.target_price = payload.target_price
    route.currency = payload.currency
    route.stops = payload.stops

    if currency_changed or stops_changed:
        for row in session.exec(
            select(PriceHistory).where(PriceHistory.route_id == track_id)
        ).all():
            session.delete(row)

    session.add(route)
    session.commit()
    session.refresh(route)
    return _to_track_read(session, route)


@app.delete("/api/tracks/{track_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_track(track_id: int, session: SessionDep, current_user: CurrentUser) -> Response:
    """Delete a tracked route and its price history."""
    route = _get_user_route(session, track_id, current_user)
    session.delete(route)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/tracks/{track_id}/booking", response_model=BookingLinkRead)
def get_track_booking_link(
    track_id: int,
    session: SessionDep,
    current_user: CurrentUser,
) -> BookingLinkRead:
    """Fetch a fresh booking URL and open the airline / aggregator site."""
    route = _get_user_route(session, track_id, current_user)

    search = _build_search_params(route)
    try:
        quote = fetch_best_quote(search, get_available_flight_clients())
    except FlightAPIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    if not quote.booking_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No booking URL available for this route",
        )

    return BookingLinkRead(
        track_id=track_id,
        url=quote.booking_url,
        airline=quote.airline,
        price=quote.price,
        currency=quote.currency,
    )


@app.get("/api/tracks/{track_id}/history", response_model=list[PriceHistoryRead])
def get_track_history(
    track_id: int,
    session: SessionDep,
    current_user: CurrentUser,
) -> list[PriceHistoryRead]:
    """Return price history for sparkline charts."""
    route = _get_user_route(session, track_id, current_user)

    rows = session.exec(
        select(PriceHistory)
        .where(PriceHistory.route_id == track_id)
        .where(PriceHistory.currency == route.currency)
        .order_by(PriceHistory.checked_at.asc())
    ).all()
    return [PriceHistoryRead.model_validate(row) for row in rows]


@app.post("/api/devices/register", response_model=DeviceRead)
def register_device(
    payload: DeviceRegister,
    session: SessionDep,
    current_user: CurrentUser,
) -> DeviceRead:
    """Register or update a device FCM token for the authenticated user."""
    existing = session.exec(
        select(UserDevice).where(UserDevice.fcm_token == payload.fcm_token)
    ).first()

    if existing:
        existing.user_id = current_user.id
        existing.email = payload.email or current_user.email
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return DeviceRead.model_validate(existing)

    device = UserDevice(
        user_id=current_user.id,
        fcm_token=payload.fcm_token,
        email=payload.email or current_user.email,
    )
    session.add(device)
    session.commit()
    session.refresh(device)
    return DeviceRead.model_validate(device)


_frontend_dist = PROJECT_ROOT / "frontend" / "dist"
_frontend_dir = _frontend_dist if _frontend_dist.is_dir() else PROJECT_ROOT / "frontend"
_frontend_index = _frontend_dir / "index.html"
_frontend_assets = _frontend_dir / "assets"

if _frontend_assets.is_dir():
    app.mount("/assets", StaticFiles(directory=_frontend_assets), name="assets")


@app.get("/")
def serve_frontend_root() -> FileResponse:
    """Serve the SPA entry point without intercepting /api routes."""
    if not _frontend_index.is_file():
        raise HTTPException(status_code=404, detail="Frontend not built")
    return FileResponse(_frontend_index)

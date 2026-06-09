"""Smoke test: notification formatting and mock dispatch."""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import Settings
from sqlmodel import Session, select

from database import engine, init_db, session_scope
from auth import hash_password
from models import User, UserDevice
from services.notification import (
    NotificationDispatchResult,
    NotificationService,
    build_drop_alert_content,
    format_price,
)
from services.scheduler import PriceDropAlert


class RecordingEmailSender:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send(self, to_email: str, subject: str, plain_body: str, html_body: str) -> None:
        self.sent.append((to_email, subject))


class RecordingPushSender:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    def send(self, token: str, title: str, body: str, data=None) -> None:
        self.sent.append((token, title, body))


def main() -> None:
    alert = PriceDropAlert(
        route_id=1,
        user_id=1,
        departure_city="JFK",
        destination_city="LHR",
        departure_date=date(2026, 9, 1),
        return_date=date(2026, 9, 10),
        previous_lowest=850.0,
        current_price=420.0,
        currency="EUR",
        target_price=500.0,
        airline="TestAir",
    )

    subject, plain, html = build_drop_alert_content(alert)
    assert "€420.00" in plain
    assert "€850.00" in plain
    assert format_price(99.5, "GBP") == "£99.50"
    assert "Price drop" in subject
    assert "<strong" in html

    init_db()
    user_id = 1
    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == "traveler@example.com")).first()
        if not user:
            user = User(
                email="traveler@example.com",
                password_hash=hash_password("secretpass"),
            )
            session.add(user)
            session.commit()
            session.refresh(user)

        user_id = user.id  # type: ignore[assignment]

        existing = session.exec(
            select(UserDevice).where(UserDevice.fcm_token == "test-fcm-token-abc")
        ).first()
        if not existing:
            session.add(
                UserDevice(
                    user_id=user_id,
                    fcm_token="test-fcm-token-abc",
                    email="traveler@example.com",
                )
            )
            session.commit()

    alert = PriceDropAlert(
        route_id=1,
        user_id=user_id,
        departure_city="JFK",
        destination_city="LHR",
        departure_date=date(2026, 9, 1),
        return_date=date(2026, 9, 10),
        previous_lowest=850.0,
        current_price=420.0,
        currency="EUR",
        target_price=500.0,
        airline="TestAir",
    )

    settings = Settings(notifications_enabled=True)
    email = RecordingEmailSender()
    push = RecordingPushSender()
    service = NotificationService(settings=settings, email_sender=email, push_sender=push)

    result = service.dispatch_drop_alerts([alert])
    assert result.alerts_processed == 1
    assert result.emails_sent == 1
    assert result.pushes_sent == 1
    assert len(email.sent) == 1
    assert email.sent[0][0] == "traveler@example.com"
    assert len(push.sent) == 1
    assert push.sent[0][0] == "test-fcm-token-abc"

    print(f"Emails dispatched: {result.emails_sent}, pushes: {result.pushes_sent}")

    with Session(engine) as session:
        user = session.get(User, user_id)
        assert user is not None
        user.email_notifications_enabled = False
        user.push_notifications_enabled = True
        session.add(user)
        session.commit()

    email.sent.clear()
    push.sent.clear()
    result = service.dispatch_drop_alerts([alert])
    assert result.emails_sent == 0
    assert result.pushes_sent == 1

    with Session(engine) as session:
        user = session.get(User, user_id)
        assert user is not None
        user.email_notifications_enabled = True
        user.push_notifications_enabled = False
        session.add(user)
        session.commit()

    email.sent.clear()
    push.sent.clear()
    result = service.dispatch_drop_alerts([alert])
    assert result.emails_sent == 1
    assert result.pushes_sent == 0

    print("Channel preference filtering OK")
    print("OK")


if __name__ == "__main__":
    main()

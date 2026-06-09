"""Email and Firebase Cloud Messaging notification services."""

from __future__ import annotations

import logging
import smtplib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

import requests
from sqlmodel import Session, select

from config import Settings, get_settings
from database import session_scope
from models import UserDevice
from services.scheduler import PriceDropAlert

logger = logging.getLogger(__name__)

CURRENCY_SYMBOLS = {
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "BGN": "лв",
    "HUF": "Ft",
    "JPY": "¥",
}


class NotificationError(Exception):
    """Raised when a notification channel fails to send."""


@dataclass
class NotificationDispatchResult:
    """Summary of a notification dispatch run."""

    alerts_processed: int = 0
    emails_sent: int = 0
    emails_failed: int = 0
    pushes_sent: int = 0
    pushes_failed: int = 0
    errors: list[str] = field(default_factory=list)


def format_price(amount: float, currency: str) -> str:
    """Format a price with currency symbol when known."""
    symbol = CURRENCY_SYMBOLS.get(currency.upper(), "")
    if symbol in {"лв", "Ft"}:
        return f"{amount:,.0f} {symbol}" if currency.upper() == "HUF" else f"{amount:,.2f} {symbol}"
    if symbol:
        return f"{symbol}{amount:,.2f}"
    return f"{amount:,.2f} {currency.upper()}"


def build_drop_alert_content(alert: PriceDropAlert) -> tuple[str, str, str]:
    """Return (subject, plain_text_body, html_body) for a price-drop alert."""
    route_label = f"{alert.departure_city} → {alert.destination_city}"
    dates = alert.departure_date.isoformat()
    if alert.return_date:
        dates = f"{dates} – {alert.return_date.isoformat()}"

    previous = format_price(alert.previous_lowest, alert.currency)
    current = format_price(alert.current_price, alert.currency)
    savings = format_price(alert.previous_lowest - alert.current_price, alert.currency)

    subject = f"Price drop: {route_label} now {current}"
    airline_line = f"\nAirline: {alert.airline}" if alert.airline else ""

    plain = (
        f"Flight price drop detected!\n\n"
        f"Route: {route_label}\n"
        f"Dates: {dates}{airline_line}\n"
        f"Previous low: {previous}\n"
        f"New price: {current}\n"
        f"You save: {savings}\n"
    )

    html = (
        f"<h2>Flight price drop detected</h2>"
        f"<p><strong>{route_label}</strong><br>"
        f"Dates: {dates}</p>"
        f"<p>Previous low: <s>{previous}</s><br>"
        f"New price: <strong style='color:#16a34a'>{current}</strong><br>"
        f"You save: {savings}</p>"
    )
    if alert.airline:
        html += f"<p>Airline: {alert.airline}</p>"

    return subject, plain, html


class EmailSender(ABC):
    """Abstract email sender."""

    @abstractmethod
    def send(self, to_email: str, subject: str, plain_body: str, html_body: str) -> None:
        """Send an email message."""


class ResendEmailSender(EmailSender):
    """Send email via the Resend HTTP API."""

    API_URL = "https://api.resend.com/emails"

    def __init__(self, api_key: str, from_email: str) -> None:
        if not api_key:
            raise NotificationError("RESEND_API_KEY is required for Resend email.")
        if not from_email:
            raise NotificationError("SMTP_FROM_EMAIL is required as the Resend from address.")
        self._api_key = api_key
        self._from_email = from_email

    def send(self, to_email: str, subject: str, plain_body: str, html_body: str) -> None:
        payload = {
            "from": self._from_email,
            "to": [to_email],
            "subject": subject,
            "text": plain_body,
            "html": html_body,
        }
        try:
            response = requests.post(
                self.API_URL,
                json=payload,
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=30,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise NotificationError(f"Resend email failed for {to_email}: {exc}") from exc


class SMTPEmailSender(EmailSender):
    """Send email via standard SMTP."""

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        from_email: str,
    ) -> None:
        if not host or not from_email:
            raise NotificationError("SMTP_HOST and SMTP_FROM_EMAIL are required for SMTP.")
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._from_email = from_email

    def send(self, to_email: str, subject: str, plain_body: str, html_body: str) -> None:
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = self._from_email
        message["To"] = to_email
        message.attach(MIMEText(plain_body, "plain"))
        message.attach(MIMEText(html_body, "html"))

        try:
            with smtplib.SMTP(self._host, self._port, timeout=30) as server:
                server.starttls()
                if self._user and self._password:
                    server.login(self._user, self._password)
                server.sendmail(self._from_email, [to_email], message.as_string())
        except smtplib.SMTPException as exc:
            raise NotificationError(f"SMTP email failed for {to_email}: {exc}") from exc


class FCMPushSender:
    """Send Android push notifications via Firebase Cloud Messaging."""

    def __init__(self, credentials_path: Optional[str] = None, credentials_dict: Optional[dict] = None) -> None:
        if credentials_dict is not None:
            self._credentials_dict = credentials_dict
            self._credentials_path = None
        elif credentials_path:
            path = Path(credentials_path)
            if not path.is_file():
                raise NotificationError(f"FCM credentials file not found: {credentials_path}")
            self._credentials_path = str(path)
            self._credentials_dict = None
        else:
            raise NotificationError(
                "FCM credentials required: set FCM_CREDENTIALS_PATH or FCM_CREDENTIALS_JSON."
            )
        self._initialized = False

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        import firebase_admin
        from firebase_admin import credentials

        if not firebase_admin._apps:
            if self._credentials_dict is not None:
                cred = credentials.Certificate(self._credentials_dict)
            else:
                cred = credentials.Certificate(self._credentials_path)
            firebase_admin.initialize_app(cred)
        self._initialized = True

    def send(self, token: str, title: str, body: str, data: Optional[dict[str, str]] = None) -> None:
        self._ensure_initialized()
        from firebase_admin import messaging

        message = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            data=data or {},
            token=token,
        )
        try:
            messaging.send(message)
        except Exception as exc:
            raise NotificationError(f"FCM push failed for token {token[:12]}…: {exc}") from exc


class NotificationService:
    """Orchestrates email and push notifications for price-drop alerts."""

    def __init__(
        self,
        settings: Settings,
        email_sender: Optional[EmailSender] = None,
        push_sender: Optional[FCMPushSender] = None,
    ) -> None:
        self._settings = settings
        self._email_sender = email_sender
        self._push_sender = push_sender

    def _get_registered_devices(
        self,
        session: Session,
        user_id: Optional[int],
    ) -> list[UserDevice]:
        statement = select(UserDevice)
        if user_id is not None:
            statement = statement.where(UserDevice.user_id == user_id)
        return list(session.exec(statement).all())

    def send_drop_alert(
        self,
        alert: PriceDropAlert,
        devices: list[UserDevice],
        result: NotificationDispatchResult,
    ) -> None:
        """Dispatch a single drop alert to all registered devices."""
        if not self._settings.notifications_enabled:
            logger.info("Notifications disabled — skipping alert for route %s", alert.route_id)
            return

        subject, plain, html = build_drop_alert_content(alert)
        push_title = subject
        push_body = (
            f"{format_price(alert.previous_lowest, alert.currency)} → "
            f"{format_price(alert.current_price, alert.currency)}"
        )
        push_data = {
            "route_id": str(alert.route_id),
            "current_price": str(alert.current_price),
            "currency": alert.currency,
        }

        emailed: set[str] = set()
        for device in devices:
            if device.email and device.email not in emailed and self._email_sender:
                try:
                    self._email_sender.send(device.email, subject, plain, html)
                    result.emails_sent += 1
                    emailed.add(device.email)
                    logger.info("Email sent to %s for route %s", device.email, alert.route_id)
                except NotificationError as exc:
                    result.emails_failed += 1
                    result.errors.append(str(exc))
                    logger.error("%s", exc)

            if device.fcm_token and self._push_sender:
                try:
                    self._push_sender.send(device.fcm_token, push_title, push_body, push_data)
                    result.pushes_sent += 1
                    logger.info("Push sent for route %s", alert.route_id)
                except NotificationError as exc:
                    result.pushes_failed += 1
                    result.errors.append(str(exc))
                    logger.error("%s", exc)

    def dispatch_drop_alerts(self, alerts: list[PriceDropAlert]) -> NotificationDispatchResult:
        """Send notifications for all price-drop alerts."""
        result = NotificationDispatchResult(alerts_processed=len(alerts))
        if not alerts:
            return result

        with session_scope() as session:
            for alert in alerts:
                user_devices = self._get_registered_devices(session, alert.user_id)
                if not user_devices:
                    logger.warning(
                        "No devices for user %s — skipping alert for route %s",
                        alert.user_id,
                        alert.route_id,
                    )
                    continue
                self.send_drop_alert(alert, user_devices, result)

        return result


def get_email_sender(settings: Settings) -> Optional[EmailSender]:
    """Build the configured email sender, or None if not configured."""
    provider = settings.email_provider.strip().lower()

    if provider == "auto":
        if settings.resend_api_key:
            provider = "resend"
        elif settings.smtp_host:
            provider = "smtp"
        else:
            return None

    if provider == "resend":
        return ResendEmailSender(settings.resend_api_key, settings.smtp_from_email)

    if provider == "smtp":
        return SMTPEmailSender(
            host=settings.smtp_host,
            port=settings.smtp_port,
            user=settings.smtp_user,
            password=settings.smtp_password,
            from_email=settings.smtp_from_email,
        )

    raise NotificationError(f"Unsupported EMAIL_PROVIDER: {settings.email_provider}")


def _parse_fcm_credentials_json(raw: str) -> dict:
    import json

    text = raw.strip()
    if not text:
        raise NotificationError("FCM_CREDENTIALS_JSON is empty.")
    if not text.startswith("{"):
        text = "{" + text
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise NotificationError("FCM_CREDENTIALS_JSON is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise NotificationError("FCM_CREDENTIALS_JSON must be a JSON object.")
    return payload


def get_push_sender(settings: Settings) -> Optional[FCMPushSender]:
    """Build the FCM push sender, or None if credentials are not configured."""
    if settings.fcm_credentials_json.strip():
        try:
            return FCMPushSender(credentials_dict=_parse_fcm_credentials_json(settings.fcm_credentials_json))
        except NotificationError as exc:
            logger.warning("FCM push disabled: %s", exc)
            return None
    if settings.fcm_credentials_path:
        return FCMPushSender(credentials_path=settings.fcm_credentials_path)
    return None


def get_notification_service(settings: Optional[Settings] = None) -> NotificationService:
    """Return a configured notification service."""
    settings = settings or get_settings()
    return NotificationService(
        settings=settings,
        email_sender=get_email_sender(settings),
        push_sender=get_push_sender(settings),
    )


def dispatch_drop_alerts(alerts: list[PriceDropAlert]) -> NotificationDispatchResult:
    """Convenience entry point used by the scheduler after price checks."""
    service = get_notification_service()
    return service.dispatch_drop_alerts(alerts)

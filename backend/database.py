"""Database engine, session management, and initialization."""

import json
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

from config import get_settings
import models  # noqa: F401 — register tables with SQLModel.metadata

settings = get_settings()

_db_url = settings.normalized_database_url()
connect_args = {"check_same_thread": False} if _db_url.startswith("sqlite") else {}
engine = create_engine(_db_url, echo=settings.is_development, connect_args=connect_args)


def _is_sqlite() -> bool:
    return _db_url.startswith("sqlite")


def _ensure_data_directory() -> None:
    """Create the SQLite data directory if it does not exist."""
    if not _is_sqlite():
        return

    db_path = _db_url.replace("sqlite:///", "")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)


def _sql_table(table_name: str) -> str:
    """Return a dialect-safe table identifier (PostgreSQL reserves ``user``)."""
    if _is_sqlite():
        return table_name
    return f'"{table_name}"'


def _debug_log(message: str, data: dict, hypothesis_id: str) -> None:
    # #region agent log
    try:
        payload = {
            "sessionId": "9d1bcb",
            "runId": "migration-fix",
            "hypothesisId": hypothesis_id,
            "location": "database.py:migrate_db",
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        log_path = Path(__file__).resolve().parent.parent / "debug-9d1bcb.log"
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload) + "\n")
    except OSError:
        pass
    # #endregion


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    """Return True when ``column_name`` exists on ``table_name``."""
    if _is_sqlite():
        rows = conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
        return any(row[1] == column_name for row in rows)

    row = conn.execute(
        text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :table AND column_name = :column LIMIT 1"
        ),
        {"table": table_name, "column": column_name},
    ).first()
    return row is not None


def migrate_db() -> None:
    """Apply lightweight schema migrations for existing databases."""
    migrations = [
        ("tracked_route", "currency", "VARCHAR(3) DEFAULT 'USD'"),
        ("tracked_route", "stops", "VARCHAR(20) DEFAULT 'any'"),
        ("tracked_route", "user_id", "INTEGER"),
        ("price_history", "currency", "VARCHAR(3) DEFAULT 'USD'"),
        ("price_history", "airline", "VARCHAR(100)"),
        ("price_history", "booking_url", "VARCHAR(2048)"),
        ("price_history", "source", "VARCHAR(50)"),
        ("price_history", "stops_count", "INTEGER"),
        ("user_device", "user_id", "INTEGER"),
        ("user", "alert_email", "VARCHAR(255)"),
        ("user", "email_notifications_enabled", "BOOLEAN DEFAULT TRUE"),
        ("user", "push_notifications_enabled", "BOOLEAN DEFAULT TRUE"),
    ]

    with engine.begin() as conn:
        for table, column, definition in migrations:
            if _column_exists(conn, table, column):
                continue
            sql = f"ALTER TABLE {_sql_table(table)} ADD COLUMN {column} {definition}"
            # #region agent log
            _debug_log(
                "running migration",
                {"table": table, "column": column, "sql": sql, "dialect": "sqlite" if _is_sqlite() else "postgresql"},
                "H1",
            )
            # #endregion
            try:
                conn.execute(text(sql))
            except Exception as exc:
                # #region agent log
                _debug_log(
                    "migration failed",
                    {"table": table, "column": column, "sql": sql, "error": type(exc).__name__},
                    "H1",
                )
                # #endregion
                raise


def init_db() -> None:
    """Create all database tables and apply migrations."""
    _ensure_data_directory()
    SQLModel.metadata.create_all(engine)
    migrate_db()


def get_session() -> Generator[Session, None, None]:
    """Yield a database session for FastAPI dependency injection."""
    with Session(engine) as session:
        yield session


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Provide a transactional scope for background jobs and scripts."""
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

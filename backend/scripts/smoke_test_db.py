"""Smoke test: initialize database and verify tables exist."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session, text

import models  # noqa: F401
from database import engine, init_db


def main() -> None:
    init_db()
    with Session(engine) as session:
        rows = session.exec(
            text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        ).all()
        tables = [row[0] for row in rows]
        expected = {"price_history", "tracked_route", "user_device", "user"}
        missing = expected - set(tables)
        if missing:
            raise SystemExit(f"Missing tables: {missing}. Found: {tables}")
        print("Tables:", tables)
        print("OK")


if __name__ == "__main__":
    main()

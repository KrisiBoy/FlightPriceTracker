"""Airport lookup and search for route autocomplete."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable

_DATA_PATH = Path(__file__).resolve().parent / "data" / "airports.json"


@dataclass(frozen=True)
class Airport:
    """A searchable airport entry."""

    iata: str
    name: str
    city: str
    country: str


@lru_cache(maxsize=1)
def load_airports() -> tuple[Airport, ...]:
    """Load the curated airport list from disk."""
    raw = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    return tuple(
        Airport(
            iata=row["iata"].upper(),
            name=row["name"],
            city=row["city"],
            country=row["country"],
        )
        for row in raw
    )


def _score_airport(airport: Airport, query: str) -> int:
    """Return a relevance score for ``query`` against an airport (higher is better)."""
    iata = airport.iata.lower()
    city = airport.city.lower()
    country = airport.country.lower()
    name = airport.name.lower()

    if iata == query:
        return 100
    if iata.startswith(query):
        return 95
    if city.startswith(query):
        return 85
    if country.startswith(query):
        return 80
    if query in iata:
        return 75
    if query in city:
        return 70
    if query in country:
        return 65
    if query in name:
        return 55

    tokens = query.split()
    if not tokens:
        return 0

    haystack = f"{iata} {city} {country} {name}"
    if all(token in haystack for token in tokens):
        return 50
    return 0


def search_airports(query: str, *, limit: int = 8) -> list[Airport]:
    """Search airports by IATA code, city, country, or airport name."""
    normalized = query.strip().lower()
    if len(normalized) < 1:
        return []

    scored: list[tuple[int, Airport]] = []
    for airport in load_airports():
        score = _score_airport(airport, normalized)
        if score > 0:
            scored.append((score, airport))

    scored.sort(key=lambda item: (-item[0], item[1].city.lower(), item[1].iata))
    return [airport for _, airport in scored[: max(limit, 1)]]

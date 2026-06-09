"""Flight stop preferences for route searches."""

SUPPORTED_STOPS: tuple[str, ...] = ("any", "direct", "connecting")
DEFAULT_STOPS = "any"

STOPS_LABELS: dict[str, str] = {
    "any": "Any",
    "direct": "Direct",
    "connecting": "Layover",
}


def normalize_stops(value: str) -> str:
    """Validate and normalize a stops preference."""
    normalized = value.strip().lower()
    if normalized not in SUPPORTED_STOPS:
        supported = ", ".join(SUPPORTED_STOPS)
        raise ValueError(f"Unsupported stops preference '{value}'. Supported: {supported}")
    return normalized


def stops_label(value: str) -> str:
    """Return a human-readable label for a stops preference."""
    return STOPS_LABELS.get(normalize_stops(value), value)

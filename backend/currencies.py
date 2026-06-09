"""Supported currency codes for tracked routes."""

SUPPORTED_CURRENCIES: tuple[str, ...] = ("USD", "EUR", "GBP", "BGN", "HUF", "JPY")
DEFAULT_CURRENCY = "USD"

# Mock/API price scaling relative to a ~USD 120–850 flight baseline.
CURRENCY_USD_FACTOR: dict[str, float] = {
    "USD": 1.0,
    "EUR": 0.92,
    "GBP": 0.79,
    "BGN": 1.8,
    "HUF": 360.0,
    "JPY": 150.0,
}

ZERO_DECIMAL_CURRENCIES: frozenset[str] = frozenset({"HUF", "JPY"})


def normalize_currency(code: str) -> str:
    """Validate and normalize a currency code to uppercase ISO 4217."""
    normalized = code.strip().upper()
    if normalized not in SUPPORTED_CURRENCIES:
        supported = ", ".join(SUPPORTED_CURRENCIES)
        raise ValueError(f"Unsupported currency '{code}'. Supported: {supported}")
    return normalized


def usd_factor(currency: str) -> float:
    """Return the mock/realistic multiplier from a USD baseline to ``currency``."""
    return CURRENCY_USD_FACTOR.get(normalize_currency(currency), 1.0)


def round_price(amount: float, currency: str) -> float:
    """Round a price appropriately for the given currency."""
    if normalize_currency(currency) in ZERO_DECIMAL_CURRENCIES:
        return float(round(amount))
    return round(amount, 2)

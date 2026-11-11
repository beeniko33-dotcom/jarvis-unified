"""Independent scraper package. Not a trading dependency."""
from .safe_fetch import SafeFetchError, safe_fetch_url

__all__ = ["SafeFetchError", "safe_fetch_url"]

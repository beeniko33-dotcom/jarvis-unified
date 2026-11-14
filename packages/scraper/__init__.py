"""Independent scraper package. Not a trading dependency."""
from .extract import PageMetadata, extract_page_metadata
from .safe_fetch import SafeFetchError, safe_fetch_url

__all__ = ["PageMetadata", "SafeFetchError", "extract_page_metadata", "safe_fetch_url"]

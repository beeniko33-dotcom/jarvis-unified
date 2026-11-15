# Public RSS/Atom headline metadata intake

## What this does
- Parses RSS 2.0 and Atom 1.0 XML bytes supplied by an upstream caller.
- Requires explicit allowlists for both feed hosts and article-link hosts.
- Stores publisher, feed URL, canonical article URL, headline, publication time, retrieval time and a content hash.
- Uses an append-only SQLite table with hash-based deduplication.
- Keeps every headline `candidate_unverified`.

## What it deliberately does not do
- No network request, crawler, scheduler or automatic feed discovery.
- No article-page fetching or full article body extraction.
- No login/paywall/CAPTCHA bypass or robots/terms circumvention.
- No sentiment score, trading signal or strategy promotion.
- No claim that public visibility grants republication rights.

The caller must review each publisher's feed terms, robots policy, copyright notice, rate limits and attribution requirements before fetching or scheduling a feed. The parser stores headlines and links only; even these may be subject to publisher terms. Feed retrieval should be separately implemented with a small request budget, cache, timeout, retry/backoff and a fixed host allowlist.

## Example
```python
from datetime import datetime, timezone
from research.public_rss import parse_public_feed, store_headlines

records = parse_public_feed(
    xml_bytes,
    publisher="Approved Publisher",
    feed_url="https://feeds.publisher.example/rss.xml",
    allowed_feed_hosts={"feeds.publisher.example"},
    allowed_article_hosts={"publisher.example"},
    retrieved_at=datetime.now(timezone.utc),
)
result = store_headlines(records, "data/public_headlines.sqlite")
```

The module is intentionally separate from market-price observations. Headlines are not market quotes and are never eligible for execution-quality or Level 3 evidence.

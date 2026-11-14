# Scraper package

This independent package provides a deliberately narrow, safe public-page metadata workflow. It is not a trading dependency and does not import or execute the original `advanced-scraper` runtime.

## Current functionality

- `safe_fetch.py` retrieves one public HTTP(S) page using the address validated during DNS resolution.
- `extract.py` returns only bounded page title, meta description, and headings; it does not return or persist page bodies or extract personal identities.

The fetcher allows standard HTTP/HTTPS ports only, rejects embedded credentials and non-public destinations, revalidates every redirect, and bounds total time, response bytes, and redirect count. Compressed responses are rejected rather than expanded without a decompression limit.

Run one authorized-page extraction with:

```bash
python -m packages.scraper https://example.com
```

The command prints JSON metadata only. Respect the target site's terms and applicable robots policy; this package does not implement crawling or robots-policy handling.

## Migration boundary

The original repository remains unchanged and is not imported as executable code. Its CLI includes credential/OTP brute-force and directory-enumeration functionality, spoofed forwarding headers, and personal-data extraction. Those features are outside Jarvis's supported scraper surface. Its API's current main revision requires a bearer token and defaults to loopback, but its scraping methods bypass this package's SSRF protections; the upstream security document describes a different, older API. See `docs/SCRAPER.md` before proposing additional migration.

Use `safe_fetch_url` as the only network entry point for future Jarvis extraction work. Crawling, robots-policy handling, and remote API exposure are not implemented.

# Scraper Integration

The original [`advanced-scraper`](https://github.com/beeniko33-dotcom/advanced-scraper) remains intact. Jarvis does not import or execute it. The currently verified source revision is `87a3f4bad64efe53b8a050cf94af6e2db6d1a7ea`.

## Verified source behavior

The source API at the verified revision exposes health plus authenticated scrape, crawl, and image-search routes, and defaults to loopback. `SECURITY_AND_OPERATIONS.md` describes an older unauthenticated module-dispatch API and is inconsistent with this code revision. Authentication alone is not sufficient for migration: the current API calls scraper methods that make their own network requests instead of using Jarvis's SSRF-safe fetcher.

The source runtime also includes credential/OTP brute-force and directory-enumeration tools, spoofed forwarding headers, and personal-data extraction. Jarvis will not import, expose, or operate those capabilities. The original source repo remains unchanged.

## Current Jarvis implementation

- `packages/scraper/safe_fetch.py` fetches one public HTTP(S) URL with DNS pinning, redirect validation, standard-port restriction, a total timeout, and response-size limits.
- `packages/scraper/extract.py` returns bounded title/description/headings only; it does not return or persist page content.

No crawler, robots-policy handling, or remote scraping API is enabled. Keep the existing fetcher local-only to the codebase until those controls are designed and tested.

## Future migration requirements

Any expansion to crawling or an API must enforce public-address validation and IP pinning on every request and redirect, bounded pages/concurrency/time/bytes, explicit same-site scope, site-policy checks, an identifiable user agent, and authenticated allowlisted operations. Do not use the upstream network client as a shortcut around these controls.

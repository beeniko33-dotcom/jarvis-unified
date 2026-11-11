# Scraper Integration Plan

The scraper is an independent package, not a trading dependency. Its complete legitimate functionality is to be imported from `advanced-scraper` with Git history preserved. Keep its CLI, crawl orchestration, parsing/extraction, media metadata, storage, scheduling, and extension points. No blanket feature reduction is intended.

## Foundation already in-tree

`packages/scraper/safe_fetch.py` implements SSRF-hardened HTTP(S) fetching:

- Scheme allowlist (`http`/`https`)
- DNS validation blocking private/loopback/link-local/metadata ranges
- Redirect revalidation
- Timeout and max-byte limits
- Rejection of credentialed URLs

All future remote fetch endpoints must use this primitive (or a successor with equal or stronger guarantees).

Remote interfaces must expose authenticated content-fetching operations only. Offensive security utilities and arbitrary code execution are not scraping features and must not be remotely exposed.

See `packages/scraper/README.md` for the integration security contract.

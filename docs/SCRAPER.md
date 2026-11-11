# Scraper Integration Plan

The scraper is an independent package, not a trading dependency. Its complete legitimate functionality is to be imported from `advanced-scraper` with Git history preserved. Keep its CLI, crawl orchestration, parsing/extraction, media metadata, storage, scheduling, and extension points. No blanket feature reduction is intended.

Remote interfaces must expose authenticated content-fetching operations only and enforce SSRF protections, request budgets, safe redirects, and resource limits. Offensive security utilities and arbitrary code execution are not scraping features and must not be remotely exposed.

See `packages/scraper/README.md` for the integration security contract.
# Scraper Integration Plan

The original `advanced-scraper` remains intact. Migration must preserve the full legitimate web-crawling, extraction, reporting and utility capability set; do not replace it with a reduced toy scraper.

## Verified source inventory

The source repository contains `advanced_scraper.py`, `api_server.py`, `orchestrator.py`, `report_gen.py`, `spyglass.py`, `wardrive.py`, `frontend/index.html`, `startup.sh` and dependency declarations.

Legitimate migration candidates include public-web URL fetching, same-site crawling, HTML parsing, public page metadata extraction, structured exports, image-result discovery, crawl orchestration, report generation, progress/status UI and local scheduling/storage utilities.

## Security findings requiring redesign

The source API currently binds to `0.0.0.0`, has no authentication, accepts a user-controlled module ID and invokes an interactive Python process through `pexpect`. Its module map includes credential/OTP brute force, exploit probes, port/subdomain scanning, TCP flooding, email/SMS bombing, reverse-shell and persistence functions. The CLI also contains stealth header spoofing, credential harvesting and deep people-search/PII collection.

**Do not import or deploy that API server as-is.** It creates a remote abuse and command-execution surface. Do not expose exploit testing, credential/OTP attacks, flooding, reverse shells, persistence, arbitrary commands or invasive personal-data dossiers through Jarvis. Those are not required for the legitimate scraper product.

This is a targeted safety boundary, not a blanket restriction on ordinary scraping. Preserve the legitimate crawler, parser, extractor, image metadata, exporter, reporting, orchestration and extensibility features.

## Required safe migration design

- HTTP/HTTPS only; reject embedded credentials and non-public destination IPs.
- Validate DNS results and pin the validated destination during connection to prevent DNS-rebinding/TOCTOU bypasses.
- Revalidate every redirect; block private, loopback, link-local, multicast, reserved and cloud-metadata ranges for IPv4 and IPv6.
- Bound connect/read timeouts, response bytes, decompression ratio, redirects, concurrency, crawl depth/page count and per-host request rate.
- Keep crawl scope explicit (same-site by default), respect robots policy and site terms where applicable, and provide an identifiable user agent.
- Separate public business/contact page extraction from people-search or sensitive personal-data aggregation.
- Use authenticated, allowlisted API operations; no interactive subprocess dispatch or arbitrary module IDs.
- Store provenance (source URL, timestamp, extraction method), support deletion/retention controls, and avoid logging harvested content or secrets.
- Keep the local CLI and approved extraction functions independently usable.

## Migration workflow

1. Preserve original repository and Git history; import into `sources/advanced-scraper` without squashing.
2. Inventory every module, dependency, CLI command and output format before moving code.
3. Add compatibility tests for each legitimate capability before changing implementation.
4. Route network access through the hardened fetch primitive (or a stronger pinned-connection implementation).
5. Rebuild the API as a narrow authenticated job interface; never expose the original `/scan/all` dispatcher.
6. Compare output behavior with the original for authorized public websites and document any intentionally excluded unsafe function.

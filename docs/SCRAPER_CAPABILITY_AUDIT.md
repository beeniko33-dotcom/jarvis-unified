# Advanced Scraper — Capability and Safety Audit

## Source checked

Repository: `beeniko33-dotcom/advanced-scraper`, branch `main`.

Inspected the README, `advanced_scraper.py`, `api_server.py`, `orchestrator.py`, `report_gen.py`, `requirements.txt`, `PRODUCTION.md` and `spyglass.py`.

## Capabilities to preserve

| Capability | Migration treatment |
|---|---|
| HTTP(S) URL fetch | Preserve through hardened, DNS-pinned safe fetch |
| Same-site crawling and spider traversal | Preserve with explicit scope, robots policy and crawl budgets |
| HTML parsing and structured page metadata extraction | Preserve for public pages and authorized targets |
| Public business contact details on pages | Preserve narrowly with provenance and privacy controls |
| Social-link extraction from public pages | Preserve as page metadata, not identity dossiers |
| Image-result discovery | Preserve with provider terms, bounded results and source attribution |
| TXT/JSON/CSV/HTML/Markdown exports | Preserve and add tests |
| Crawl orchestration and report generation | Preserve with job IDs, cancellation and audit logs |
| Local CLI, status UI and scheduling/storage extension points | Preserve after dependency and interface inventory |

## Unsafe or privacy-invasive features not to expose

- Login/password and OTP brute forcing
- Exploit probes, injection attacks and vulnerability exploitation against arbitrary targets
- Port/subdomain enumeration without explicit authorization controls
- TCP flooding and email/SMS bombing
- Reverse-shell listeners, payload generation, persistence and arbitrary command execution
- Deep people-search and bulk collection of personal phone numbers, home addresses or identity dossiers
- The current unauthenticated `0.0.0.0` API dispatcher using `pexpect` to launch interactive modules

The old API's `/scan/all` route chains together the entire module list. It must not be ported. Replace it with authenticated, allowlisted scraping jobs and a localhost-only development default.

## High-priority engineering defects to address

1. The original network client does not use the unified SSRF-safe fetch layer.
2. DNS validation must be tied to the actual socket connection; validating DNS and then allowing the HTTP library to resolve again leaves a rebinding race.
3. Crawl concurrency, response bytes, decompression, total runtime and per-host rate budgets need hard limits.
4. User-controlled paths and filenames need safe normalization; output directories and retention must be explicit.
5. API authentication, authorization, job isolation, cancellation, structured errors and audit trails are absent.
6. `spyglass.py` stores target-derived filenames and invokes local speech/vibration commands; keep platform-specific notification adapters local and sanitize output paths.
7. `report_gen.py` infers vulnerability hits from text matching; reports must distinguish raw observations from verified findings.

## Acceptance tests before migration

- Unit tests for URL normalization, IPv4/IPv6 blocking, DNS pinning, redirect checks and size/time budgets.
- Local fixture-site tests for same-site crawling, canonical URLs, duplicate handling and extraction correctness.
- Golden tests for export formats and report schemas.
- API tests proving unauthenticated requests fail, unsupported operations are rejected and remote clients cannot execute local commands.
- Regression comparison against the original for every approved scraper capability.

**Policy:** Preserve the complete legitimate scraper product. Do not preserve unsafe remote attack execution or invasive personal-data aggregation as features.

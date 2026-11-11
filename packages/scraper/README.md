# Scraper package integration boundary

This directory is reserved for the history-preserving import of the complete legitimate `advanced-scraper` codebase. Do not replace it with a reduced toy scraper. Preserve supported CLI workflows, parsers, crawl scheduling, storage backends, content extraction, media metadata, normalization, and plugin interfaces after an inventory and compatibility pass.

## Current foundation (pre-import)

`safe_fetch.py` provides an SSRF-hardened HTTP(S) fetch primitive:

- Scheme allowlist: `http`, `https` only
- Blocks loopback, private, link-local, multicast, reserved, and cloud-metadata ranges
- DNS resolution validation + redirect revalidation
- Timeouts, max response size, max redirects
- No shell, no local module execution, no credentialed URLs

Use this module as the only network entry point when exposing any remote fetch API later.

## Security contract for network fetching

- Support broad public-web crawling and extraction, subject to site terms, robots policy where applicable, and configured rate limits.
- Permit only explicitly supported URL schemes (normally HTTP/HTTPS).
- Resolve hostnames and reject loopback, private, link-local, multicast, reserved, and cloud-metadata destinations, including IPv4-mapped IPv6.
- Revalidate every redirect and every DNS resolution to mitigate rebinding.
- Bound connect/read timeouts, response bytes, decompression ratio, redirect count, concurrency, and per-host request rate.
- Never expose arbitrary local module execution, shell commands, exploit testing, brute-force, flooding, or reverse-shell functions through a remote API.
- Keep the standalone local CLI and legitimate extraction features independently usable.

The original `advanced-scraper` repository remains untouched. Import its Git history in a separate migration step after file-by-file capability and dependency review.

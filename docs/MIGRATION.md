# Migration Map — Source of Truth

This document records the seven source repositories and migration strategy.

| Capability | Primary source repository | Status |
|---|---|---|
| Core bot structure, status server, mobile stubs | `jarvis-trader-ecosystem` | Foundation migrated; history import pending |
| Deriv execution engine, risk rules, Docker/Caddy, MCP | `jarvis-ai-trading-system` | Demo adapter must be rebuilt behind central risk gate |
| Signal bot logic | `jarvis-trader` | Inventory and regression migration pending |
| Next.js dashboard | `jarvistrader` | Existing dashboard is a status-only skeleton; frontend migration pending |
| Research / signal concepts | `quantum-peak-pro` | Inventory before porting |
| Multi-agent brain, memory, TTS ideas | `jarvis-ai` | Inventory and dependency/security review pending |
| Full scraper toolkit | `advanced-scraper` | Source inventory completed; safe capability migration and history import pending |

## Source repositories and branches

- `jarvis-trader-ecosystem` — `main`
- `jarvis-ai-trading-system` — `main`
- `jarvis-trader` — `main`
- `jarvistrader` — `main`
- `quantum-peak-pro` — `main`
- `jarvis-ai` — `master`
- `advanced-scraper` — `main`

## Migration strategy

1. Keep all seven original repositories intact; no archive or delete operations are part of migration.
2. Use `scripts/import_sources.sh` on a clean local clone with GitHub SSH access. It uses `git subtree add` without `--squash`, preserving source ancestry.
3. Verify imported source heads and ancestry with `git log --graph --all`.
4. Inventory dependencies, interfaces and tests before selective migration into the unified runtime.
5. Preserve all legitimate scraper capabilities. See `docs/SCRAPER_CAPABILITY_AUDIT.md` for the source audit and safe migration boundary.
6. Record source commit SHAs, imported paths, and regression results here.

## Important scraper source audit

The original `advanced-scraper` includes ordinary web scraping and reporting, but also an unauthenticated API bound to `0.0.0.0` that dispatches module IDs through an interactive subprocess. Its advertised modules include credential/OTP brute force, exploit probes, port/subdomain scanning, TCP flooding, email/SMS bombing, reverse-shell and persistence functions; its CLI also includes invasive people-search/PII aggregation.

Do not migrate or expose that API as-is. Preserve public-web crawling, parsing, authorized page extraction, image-result discovery, export, reporting and orchestration. Unsafe attack, flooding, persistence, arbitrary-command and invasive personal-data functions are not part of the remotely exposed Jarvis scraper.

## Import limitation

The history-preserving import script requires a clean local Git clone and SSH access to all seven source repositories. GitHub API edits cannot execute that local Git operation or verify subtree ancestry. Run it locally after the current branch is merged, then submit the import and regression evidence for review.

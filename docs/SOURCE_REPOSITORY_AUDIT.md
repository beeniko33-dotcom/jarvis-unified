# Seven-Repository Source Audit

This is a README/tree-level inventory of the six non-scraper source repositories plus the separate scraper code audit. It is not a complete line-by-line code review. Original repositories remain unchanged.

| Source | Observed contents | Integration assessment |
|---|---|---|
| `jarvis-trader-ecosystem` | Nested Python app, predictors, status server, security module/tests, Expo and Flutter clients, Docker and CI | Best source for app foundation and mobile. Inspect nested/root duplicate entry points and verify ML claims with tests before porting. |
| `jarvis-ai-trading-system` | Deriv client, live server, config/journal stores, strategy, optimizer, backtester, MCP server, Docker/Caddy deployment, tests | Strongest Deriv integration candidate. Rebuild as a broker adapter behind Jarvis risk/execution contracts; retain demo/locked defaults and audit every order path. |
| `jarvis-trader` | Compact RSI/pattern signal bot, Telegram interface and status server | Candidate strategy/notification source. Validate signal calculations, dependencies and SQLite semantics before porting. |
| `jarvistrader` | Next.js Rise/Fall trading terminal, Deriv WebSocket provider, OAuth/auth hooks, chart and position components | Candidate dashboard frontend. Audit OAuth scopes, client-side environment exposure and all trade/sell paths before integration. |
| `quantum-peak-pro` | Minimal landing page, MCP bridge and requirements; README explicitly identifies the project as a skeleton | No production strategy should be assumed. Treat as research notes only until a real tested engine exists. |
| `jarvis-ai` | Python/Flutter assistant, API bridge, multi-agent/AI and build tooling | Large source tree requires focused module inventory. Tree includes generated `__pycache__`, logs, output files and a `chroma_db` directory; exclude generated/binary artifacts from selective migration unless deliberately needed and reviewed. |
| `advanced-scraper` | Web crawler/extractors/reports plus high-risk offensive and personal-data functions | See `SCRAPER_CAPABILITY_AUDIT.md`; preserve legitimate scraping only and rebuild the API safely. |

## Cross-repository risks

1. **Credential hygiene:** the ecosystem README records that credential files were previously committed and calls for rotation of affected Telegram/MT5 credentials. Audit Git history and rotate any still-valid credentials that may have been exposed. Do not copy secrets into Jarvis Unified.
2. **Duplicate implementations:** ecosystem contains root and nested app structures. Select one canonical implementation after comparing tests and behavior.
3. **Execution duplication:** the Deriv terminal and Rise/Fall frontend each have their own execution paths. Do not connect them directly to the unified runtime until all orders use the central risk gate and idempotent broker contract.
4. **Maturity mismatch:** Quantum Peak Pro explicitly describes itself as Level 0. Do not inherit claims of accuracy from repository names or older marketing copy.
5. **AI data hygiene:** do not import generated caches, local logs, personal datasets or vector DB state into source control without explicit need, ownership review and retention policy.
6. **No blind merge:** source repositories remain intact; import history first, then selectively migrate modules with regression tests.

## Next engineering sequence

1. Complete history-preserving subtree imports locally using `scripts/import_sources.sh`.
2. Create a source manifest recording exact source commit SHAs and license/ownership checks.
3. Port and test the Deriv data client in read-only/demo mode, then adapt its execution behind the unified risk gate.
4. Port signal logic with deterministic fixtures and out-of-sample evaluation.
5. Migrate frontend and mobile clients only after a stable authenticated API contract exists.
6. Inventory AI modules and dependencies; remove generated artifacts and isolate any personal data.
7. Keep the paper-only gate engaged until Level 3 evidence has been collected and reviewed.

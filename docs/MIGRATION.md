# Migration Map — Source of Truth

This document records the origin of capabilities and the import strategy for the seven original repositories.

| Capability | Primary Source Repository | Notes |
|------------|---------------------------|-------|
| Core bot structure, status server, mobile stubs | `jarvis-trader-ecosystem` | Security PR #1 reviewed and merged; originals remain available |
| Deriv execution engine, risk rules, Docker/Caddy, MCP | `jarvis-ai-trading-system` | Demo adapter must be rebuilt behind the new risk gate |
| Signal bot logic | `jarvis-trader` | RSI correction PR remains draft pending author readiness |
| Next.js dashboard | `jarvistrader` | Environment-file cleanup/build PR remains draft |
| Research / signal concepts | `quantum-peak-pro` | Inventory before porting; do not assume production maturity |
| Multi-agent brain, memory, TTS ideas | `jarvis-ai` | CI repair PR remains draft despite passing PR checks |
| Full scraper toolkit | `advanced-scraper` | Full legitimate feature set to be preserved; API SSRF issue blocks PR #3 |

## Source repositories and branches

- `jarvis-trader-ecosystem` — `main`
- `jarvis-ai-trading-system` — `main`
- `jarvis-trader` — `main`
- `jarvistrader` — `main`
- `quantum-peak-pro` — `main`
- `jarvis-ai` — `master`
- `advanced-scraper` — `main`

## Migration strategy

1. Keep all seven original repositories intact; no archive or delete operations are part of this migration.
2. Use `scripts/import_sources.sh` to import each source under `sources/<repository>` with `git subtree add` and **without** `--squash`. This preserves original commit ancestry in the unified repository.
3. Verify each imported subtree by inspecting `git log --graph --all` and comparing the source branch head with the imported ancestry.
4. Inventory each source tree and selectively migrate modules into the target runtime. Resolve naming/dependency conflicts deliberately; do not blindly copy over the new core.
5. Preserve the scraper CLI, crawlers, parsers, extractors, scheduling, storage, media metadata, and extension points. Secure remote URL fetching against SSRF, DNS rebinding, unsafe redirects, and resource exhaustion without imposing arbitrary reductions on legitimate extraction features.
6. Record source commit SHAs, imported paths, and test results in this document.

## Pull-request audit

Eight open PRs were reviewed. The Telegram access-control PR in `jarvis-trader-ecosystem` (#1) had a successful CI run and was merged. Several other PRs have passing CI but remain drafts, so they were not merged without their author marking them ready. The scraper API PR (#3) remains blocked by missing SSRF protections. The documentation-only scraper PR (#2) also remains draft.

The seven original repositories remain available. A PR merge updates its source repository but does not replace or delete that repository.

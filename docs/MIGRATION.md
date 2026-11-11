# Migration Map — Source of Truth

This document records where each capability in `jarvis-unified` originates.

| Capability | Primary Source Repository | Notes |
|------------|---------------------------|-------|
| Core bot structure, status server, mobile stubs, maturity docs | `jarvis-trader-ecosystem` | Architectural starting point |
| Deriv live/demo execution, risk limits, Docker+Caddy, MCP | `jarvis-ai-trading-system` | Strongest recent execution code |
| Autonomous signal bot logic | `jarvis-trader` | FundedNext-oriented signals |
| Next.js web dashboard | `jarvistrader` | Deriv App Builder UI |
| Signal / research concepts | `quantum-peak-pro` | Extract ideas only (was skeleton) |
| Multi-agent brain, vector memory, TTS ideas | `jarvis-ai` | Older but useful AI components |
| Full scraper toolkit | `advanced-scraper` | Preserved as independent package |

## Migration Strategy

1. **New repository** created (`jarvis-unified`) — all original repos left untouched.
2. **Capability-first** import: we bring over working modules deliberately rather than dumping entire trees.
3. **History** can be preserved later via `git filter-repo` / subtree if desired for specific packages.
4. Original repositories will eventually receive a README banner pointing here and can be archived after validation.

## Open Pull Requests (as of creation date)

There were 8 open PRs across the source repositories. These should be reviewed individually before any of their changes are selectively ported.

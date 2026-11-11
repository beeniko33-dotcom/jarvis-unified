# Diagnostic Report — Jarvis Unified

## Baseline retrieved from GitHub

The repository is a private Python 3.11+ project with a standard-library runtime and a unittest CI workflow. The last documented/confirmed baseline on main is Level 2 operational tooling.

## Confirmed by source inspection

- Paper-only configuration and an environment-enforced kill switch
- Central RiskEngine and ExecutionService
- Paper broker with in-memory positions, realized PnL, mark-to-market valuation, configurable fees/slippage and JSONL fill ledger
- Localhost-only read-only status API and static dashboard
- Disabled Deriv/MT5 adapters
- SSRF-aware public HTTP(S) fetch primitive
- Paper-session runner and unit-test suite

## Gaps found

1. Paper ledger lacked post-fill equity, balance, realized-PnL and open-position snapshots, limiting meaningful drawdown reporting.
2. Paper session closed positions at their entry average instead of the simulated post-mark price, so the sample did not realize its marked movement.
3. No ledger analytics command or explicit multi-day evidence gate existed.
4. Paper broker state is not recovered from the ledger after restart.
5. Strategy/signal IDs and market-data provenance are not yet captured in a complete audit record.
6. Risk model lacks unrealized daily loss, daily reset/timezone, peak-equity drawdown, stale-price, leverage and correlation controls.
7. Full advanced-scraper source history and feature set remain pending import and regression.
8. Deriv/MT5 execution adapters and deployment-grade authenticated controls are not implemented.

## Changes on level-3-paper-validation

- Append account snapshots to each paper fill ledger row.
- Close the deterministic paper session at its simulated market prices.
- Add `scripts/paper_report.py` for realized-event metrics, win/loss counts, expectancy, profit factor, equity drawdown and day-span checks.
- Add automated report tests and `docs/LEVEL_3_RUNBOOK.md`.

## Verification status

These changes have been committed to the working branch. GitHub Actions must complete successfully before treating the branch as CI-verified. No local test execution, sustained multi-day paper observation, or live-broker validation is claimed here.

## Next

1. Run CI and fix all failures.
2. Run a controlled paper session and verify the generated report.
3. Collect at least 30 days of append-only paper data with complete strategy/data attribution.
4. Import the original scraper history locally and regression-test the complete legitimate feature set.
5. Keep live trading disabled.

# Architecture — Jarvis Unified

## Execution flow

Strategies and research produce broker-neutral intents. New entries pass through the central risk engine and ExecutionService before reaching the paper broker. The scraper is an independent research/data package and is not an execution dependency.

```
Research / signals -> Risk engine -> ExecutionService -> Paper broker
                                      |
                                  Audit ledger
                                      |
                              Portfolio / reports
```

## Enforced boundaries

1. Broker-neutral order, position, account and result models.
2. One execution gate for new orders.
3. Risk-reducing closes remain available when the entry kill switch is engaged.
4. Fail-closed startup: paper mode only, kill switch on by default, status API bound to localhost.
5. Scraper remote fetching uses SSRF protections; arbitrary remote code execution is not a scraper feature.
6. Deriv/MT5 adapter construction remains disabled.

## Current implementation

- Broker contract: `brokers/base.py`
- Paper simulation: `brokers/paper/`
- Models, risk and execution: `core/`
- Status API: `apps/api/status.py`
- Dashboard: `apps/dashboard/`
- Scraper fetch foundation: `packages/scraper/safe_fetch.py`
- Paper session runner: `scripts/paper_session.py`
- Ledger analytics: `scripts/paper_report.py`

## Known limitations and upgrade priorities

- Paper broker state remains in-memory; JSONL is an audit trail, not restart recovery or a transactional database.
- Ledger currently captures fill-level account snapshots but lacks tamper-evident hash chaining and complete session/strategy attribution.
- Risk controls still need unrealized daily loss, daily reset/timezone policy, peak-equity drawdown, stale-price checks, leverage/margin and correlated exposure.
- The current signal contract is not a complete research engine; signal quality requires sourced market data, strategy IDs and out-of-sample attribution.
- The scraper is a secure fetch foundation, not yet the full advanced-scraper feature set. Preserve and regression-test all legitimate original capabilities during history-preserving import.
- Status API is development-only, unauthenticated and read-only; do not expose it publicly.
- No Deriv/MT5 demo or live adapter is implemented.

## Maturity

Level 2 is the last confirmed baseline. The Level 3 branch adds paper-ledger metrics and a runbook. Level 3 requires sustained multi-day paper evidence and review, not merely code or green CI. Live trading remains locked.

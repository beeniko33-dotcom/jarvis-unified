# Architecture — Jarvis Unified

## High-level design

```
Interfaces (web / Telegram / mobile / MCP)
                 |
       Local Status & Control APIs
                 |
       Core Orchestration Services
       |       |        |       |
     Brain   Signals   Risk   Portfolio
                         |
                 Execution Service
                         |
             Broker-neutral contract
             /        |         \
          Paper     Deriv demo  MT5 demo
                         (future)
                 
       Independent packages/scraper
       (research input; not an execution dependency)
```

## Enforced boundaries

1. **Broker-neutral models:** strategies use shared order, position, account, and result types.
2. **Single execution gate:** new orders flow through `core.execution.ExecutionService`, which calls the central risk engine before reaching an adapter.
3. **Risk-reducing exits:** closing an existing position remains available while the entry kill switch is engaged. The paper adapter calculates the exact opposite-side quantity.
4. **Fail-closed startup:** only paper mode is accepted. The kill switch is engaged by default and cannot be disabled by environment configuration. Status binds to localhost only.
5. **Independent scraper:** scraper functionality is migrated as a separately configured package and must not gain arbitrary remote code execution.

## Current implementation

- Broker contract: `brokers/base.py`
- Paper simulation: `brokers/paper/`
- Shared models: `core/models.py`
- Risk gate: `core/risk/`
- Execution gate: `core/execution.py`
- Runtime config: `core/config.py`
- Read-only status endpoints: `apps/api/status.py`
- Entrypoint: `main.py`

## Known limitations

The current paper broker is in-memory only. It does not persist orders, model margin or fees, calculate mark-to-market equity, simulate slippage, or reconcile external broker state. Risk controls do not yet include portfolio correlation, leverage, drawdown, stale-price, or daily-reset policy. The status API is read-only and intended for localhost development.

No Deriv or MT5 adapter is implemented. No live execution mode exists.

## Next phases

1. Validate the current test suite in GitHub Actions and fix any failures.
2. Add persistent paper ledger, valuation, fees/slippage model, and status API integration tests.
3. Import all seven source repositories with original Git histories using a verified history-preserving migration process; retain the source repositories unchanged.
4. Inventory scraper capabilities and dependencies, then migrate all legitimate CLI/crawl/extraction features; add DNS/IP/redirect SSRF protections and resource budgets to remote fetch APIs.
5. Build dashboard status-only UI, then add demo broker adapters behind the same execution gate.
6. Run sustained paper validation before considering any higher maturity level.

# Jarvis signal intelligence and market-data pipeline

**Status:** database foundation deployed; source ingestion and strategy-to-paper wiring remain gated.

## Provider routing

| Source | Intended use | Trust ceiling |
|---|---|---|
| Biquote | EUR/USD candidate bid/ask stream via the existing SignalR collector | `candidate_unverified`; zero evidence credit |
| Deriv | Secondary comparison only for exact symbols returned by `active_symbols` | Candidate until provider-origin assurance passes |
| Twelve Data | Independent FX reference / reconciliation where the plan permits the needed cadence | Reference only; do not assume free streaming or tick entitlement |
| Gate.io | Crypto spot market data only | Not a substitute for conventional OTC EUR/USD FX |

Never infer a Deriv EUR/USD symbol from a different instrument. The last documented smoke test found no canonical `FRXEURUSD` symbol; repeat a read-only catalog check before enabling any subscription.

## Canonical signal record

The private table `jarvis_private.market_signals` stores:

- Identity: `signal_id`, idempotency key, instrument, asset class, direction, timeframe, strategy/version.
- Lineage: provider, linked observation, signal creation/expiry timestamps, and trust classification.
- Quote: bid, ask, mid, spread, provider timestamp, receive timestamp, quote age and freshness flags in `quote`.
- Analysis: indicator values, multi-timeframe alignment, trend/structure, support/resistance, evidence and conflicting evidence in `analysis`.
- Plan: entry zone, invalidation, stop, targets, reward/risk and execution assumptions in `trade_plan`.
- Risk: proposed size, account risk fraction, exposure and risk-rule outcomes in `risk`.
- Lifecycle: research/paper eligibility, paper execution details and eventual outcome.

JSON payloads are versioned by the producer. Persist provider timestamps separately from collector receive time. Use bid/ask—not mid alone—for simulated fills. Include spread, modeled slippage, fees and latency assumptions in the paper execution record.

## Non-negotiable invariants

1. `evidence_credit` is constrained to false in this phase. A live quote is not an authenticated quote.
2. Candidate/unverified signals remain research-only until feed quality, provenance and risk gates are separately reviewed.
3. A signal is not an order. Only the paper engine may consume paper-eligible signals, and only with the paper kill switch explicitly released for a controlled session.
4. Idempotency keys prevent duplicate signal ingestion. Observation IDs provide traceability.
5. Expired, stale, future-dated, malformed, out-of-order or wrong-symbol observations are rejected or quarantined.
6. No API credentials are required for public market-data collection. Never store broker secrets in observations or signal JSON.
7. No live execution, wallet signing, broker order endpoint, or account-authenticated action is part of this pipeline.

## Deployment state and remaining gates

- Supabase migration creates the private signal ledger and lookup indexes. RLS is enabled; browser roles are denied; service-role access is granted for trusted server-side ingestion.
- Existing private tables already include market observations, paper accounts, paper ledger events, paper runs, runtime audit events and worker heartbeats.
- Cloudflare remains a control/HTTP-ingestion boundary, not a long-running WebSocket collector. The Worker source now includes a `/market-data` proxy route to the JWT-protected Supabase ingestion function; this route is committed but not deployed pending Worker Python runtime validation and out-of-band secret configuration. Keep a persistent collector or provider push source outside request-lifetime Workers.
- Do not enable the Cloudflare Cron worker until the service-role secret is configured out-of-band and Python Worker runtime + heartbeat are verified.
- Do not enable paper-session execution in Cloudflare until Postgres transactional account updates, idempotency, event-chain verification and crash recovery are implemented and tested.
- The existing Biquote collector still writes to local SQLite. The hosted ingestion endpoint now exists, but the collector-to-edge adapter, endpoint secret configuration, and a real read-only end-to-end smoke test are still required before continuous observations reach the hosted ledger.
- Provider provenance remains blocked. No Level 3 clock starts and no performance claim is warranted.

## Read-only operational checks

After ingestion is deployed, monitor per-source last event time, quote age, spread, reject count, duplicate count, gaps, reconnects, queue drops, clock skew and divergence between independent sources. Alert on stale/no data and fail closed rather than carrying forward old prices.

## Rollout sequence

1. Schema (deployed).
2. Contract and validation tests.
3. Server-side observation ingestion with strict schema validation, idempotency and rate limits.
4. Signal generation and audit persistence.
5. Paper execution integration with bid/ask, slippage, fees, risk limits and transactional state.
6. Independent feed provenance review and sustained forward validation.

No paid plan or service was provisioned by this change.

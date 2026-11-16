# Mandatory 30-day demo evidence gate for live-trading requests

## Policy

Every account requesting live trading must first complete at least **30 consecutive UTC calendar days in demo mode**. The 30-day count is not a guarantee of profitability and does not by itself grant live access.

The gate requires:
- a trusted, integrity-checked append-only demo ledger;
- 30 uninterrupted UTC calendar days (a missing day restarts the streak);
- at least 100 realized trade events;
- positive expectancy after commissions and slippage;
- profit factor of at least 1.2;
- maximum drawdown no greater than 10%;
- recorded risk-rejected-entry rate and complete slippage coverage;
- all demo positions closed and reconciled at assessment time.

Thresholds are prototype defaults and must be configurable only through reviewed policy changes, not by a user, strategy or learning agent.

## Outcomes

1. Any missing, invalid, incomplete or failed criterion returns `blocked`.
2. Passing the quantitative demo criteria is only a metrics result. The current prototype still returns `blocked` because trusted demo-ledger ingestion, provider authenticity and demo-account identity attestation are not implemented.
3. A separate independent check must attest provider authenticity, demo-account identity, ledger provenance, security posture and risk configuration.
4. A separate explicit owner approval and a reviewed live-adapter release are required before any live capability can be enabled.
5. The live adapter must continue to enforce the central risk engine, position/exposure limits, durable idempotency and emergency stop. Risk-reducing exits and emergency close behavior require their own tested design.

## Current prototype limitations

- `JARVIS_MODE` accepts paper mode only.
- The repository currently has no authenticated Deriv demo execution adapter; the existing paper broker is simulated and is not a Deriv demo account.
- The current paper report cannot calculate risk-rejected-entry rate and often has no slippage coverage, so it cannot satisfy this gate.
- Local hashes prove integrity of recorded bytes, not provider authenticity or that the records came from a broker demo account.
- The live-readiness assessor is deliberately not wired to enable execution. Its quantitative pass result is not an approval; the current integration gaps keep the overall result blocked.

Therefore the 30-day clock must not start from synthetic fixtures, historical replay, CI, screenshots, imported spreadsheets, process heartbeats or simulated fills. It starts only after a future demo adapter and trusted evidence collector are implemented and independently validated. The demo evidence may inform the decision, but cannot prove that live execution will be profitable or safe.

## Implementation

`research/live_readiness.py` provides a deterministic, non-executing quantitative policy assessor. It fails closed when required evidence is absent and always states that independent attestation, owner approval and live-adapter implementation remain outstanding.

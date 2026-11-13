# Deriv EUR/USD read-only market-data collector

## Scope and safety

This collector connects only to Deriv's public market-data WebSocket:
\`wss://api.derivws.com/trading/v1/options/ws/public\`. It does not authenticate an account,
request proposals, submit orders, read balances, or access the demo/real trading endpoints.
No API token or App ID is needed for this public market-data stream. Deriv documents
\`active_symbols\`, \`ticks\`, and \`ticks_history\` as public market-data calls.

The collector resolves the EUR/USD symbol dynamically from \`active_symbols\`, subscribes to
ticks, validates the symbol/price/epoch, records the raw provider message and SHA-256 digest,
and writes append-only candidates to the forward-validation SQLite store. The store enforces
freshness, UTC normalization, duplicate protection and its own hash chain.

## Provenance limits — read carefully

Deriv's public tick documentation does not describe per-message digital signatures. The
collector uses TLS certificate-chain and hostname validation for the fixed Deriv WSS hostname,
then binds normalized values to the exact raw WebSocket message and records the endpoint and
collector receive time. This is authenticated transport provenance, not a Deriv-signed payload,
not non-repudiation, and not independent third-party attestation. The callback is local
application verification; it must not be described as a cryptographic provider signature.

Before this source is accepted as final Level 3 provenance, independently review the endpoint,
TLS verification behavior, raw-message retention, instrument mapping, clock synchronization,
and Deriv's applicable data terms. If independent audit requires a signed feed, keep evidence
blocked until Deriv supplies a supported signature mechanism or an independently trusted
attestation path.

## Install and run

\`\`\`bash
pip install -e '.[market-data]'
python -m research.deriv_feed --duration-seconds 3600
\`\`\`

The default database is \`var/deriv_eurusd_forward.sqlite3\`. Use a persistent machine and
append-only backups. Keep the collector process running and check the daily report. The first
run does not establish 30 days; no observation is backfilled. Missed UTC days break the streak.

## Evidence classification

- Newly received Deriv public ticks can be recorded as unverified forward market-data candidates.
- These candidates receive no provider-verification evidence credit until a trusted connection
  attestation or independently auditable provenance mechanism is implemented.
- They are not trade fills or strategy PnL. A separate paper strategy/execution ledger is
  required for entries, exits, fees, slippage, open positions and performance statistics.
- Historical replay, CI fixtures, deterministic smoke tests, and synthetic/demo messages do
  not count toward the 30-day forward requirement.
- A 30-day market-data streak alone does not certify strategy performance or Level 3.

## Strategy metadata

Initial metadata is \`sma-crossover-long\` version \`1.0.0\`, matching the repository's
historical-replay baseline. The collector does not execute that strategy or create orders.

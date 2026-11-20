# Deriv MT5 bridge: implementation contract

## Provider and supported route

Deriv MT5 is the selected Forex CFD provider. The documented Deriv MT5 APIs manage account settings, list/create accounts and handle deposits/withdrawals; they do not place MT5 trades. The official documentation says MT5 trading is performed in the MT5 application. The new public Deriv WebSocket trading API documents options contracts, not an MT5 FX order endpoint.

Accordingly, Jarvis will integrate through a user-operated MetaTrader 5 terminal and a dedicated Expert Advisor (EA), not by calling an assumed Deriv REST order API.

## Phase A — read-only telemetry

The EA must publish:
- broker/server identity and MT5 account login identifier (pseudonymized in logs);
- allowlisted symbol metadata and contract specifications;
- bid/ask, spread, quote timestamp and server timestamp;
- candle snapshots with timeframe and completeness;
- open positions and account equity/balance only when user enables the account telemetry scope;
- EA version, connection heartbeat and terminal trade-permission state.

Bridge must reject stale quotes, unexpected server/account changes, unknown symbols, replayed nonce values, invalid signatures and clock skew outside a strict configured window. Read-only mode must not send order instructions to the terminal.

## Phase B — demo-only intent channel (not activated)

When separately authorized, demo intents must carry a unique idempotency key, approved symbol, direction, volume, stop-loss, take-profit, maximum spread, expiry and policy decision reference. The EA must independently validate account type is demo, trade permissions, symbol, volume/minimum/step, market session, stop distances and kill-switch state before any demo order. It returns accepted/rejected, ticket, fill price, slippage and reason.

Never retry an uncertain order blindly. Reconcile against terminal positions/history by idempotency tag before any retry. Duplicate intents must be rejected.

## Transport and security

- TLS only; per-install rotated credentials held server-side.
- HMAC or asymmetric request signing, timestamp + one-time nonce, replay cache.
- Strict account binding and scoped credentials; no credential in URL or logs.
- Rate limits, request-size caps, schema validation and audit log.
- Network allowlist where feasible; do not expose an unauthenticated listener on the user's PC.
- Every command checked against the Jarvis policy service and kill switch.
- No arbitrary shell, file, DLL or script execution through the bridge.

## Operational acceptance tests

1. Terminal disconnected / EA stopped → status unhealthy, no new intents.
2. Stale or replayed quote → rejected and signal suppressed.
3. Wrong account/server or real account during demo-only phase → hard reject.
4. Unknown symbol / invalid lot step / stop distance → hard reject.
5. Duplicate or timed-out intent → reconcile, never double-submit.
6. Kill switch or entries paused → no new orders.
7. Terminal reconnect → re-authenticate and reconcile before resuming.
8. Audit event records actor, policy decision, intent ID and terminal response without secrets.

## Current non-claims

No MT5 terminal is connected in this workspace. No EA has been compiled or installed, no Deriv account has been authenticated, and no market data or trades are flowing. This document does not authorize demo or live orders.

# MT5 adapter

The order adapter remains deliberately disabled. Construction raises
`RuntimeError`; this package does not submit, modify, or close orders.

## Read-only telemetry

`telemetry.py` provides pure validation models for MT5 quote and terminal
heartbeat observations. It checks:

- explicit symbol allowlists and positive bid/ask values;
- bid/ask ordering and timezone-aware timestamps;
- quote freshness and bounded future clock skew;
- expected Deriv MT5 server and pseudonymized account fingerprint;
- non-empty one-time nonce and connected terminal heartbeat.

These checks are necessary but not sufficient for a production bridge. The
transport must additionally authenticate signed requests, enforce nonce
uniqueness/replay protection, bind credentials to one account, rate-limit
requests, and persist auditable observations. No listener, EA, credentials,
or network connection is provisioned by this package.

## Execution boundary

No demo or live order channel is enabled. Do not remove the fail-closed
adapter or production controls as part of telemetry work. Any later demo
execution requires a separately reviewed EA bridge, independent demo-account
verification, end-to-end reconciliation tests, and explicit authorization.

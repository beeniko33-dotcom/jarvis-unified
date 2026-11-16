# Deriv demo-account trust boundary

**Status:** design contract only. This document does not enable a broker adapter, authenticate an account, or create trading evidence.

## Current implementation boundary

- The supported runtime remains `JARVIS_MODE=paper`.
- `brokers/deriv/adapter.py` remains intentionally disabled.
- `research/deriv_feed.py` is a public, read-only market-data collector. Its TLS session and local hashes do not prove account identity, fill authenticity, or economic truth.
- The demo adapter tracked by issue #81 must not be wired into the runtime until its protocol, security, and operational tests pass.

## Trust claims must remain separate

A future demo integration must represent these as distinct facts; one must never imply another:

| Claim | Evidence required | What it does not prove |
|---|---|---|
| Transport peer authenticated | TLS certificate and hostname validation on the established socket | Account ownership or transaction authenticity |
| API authorization accepted | Successful provider authorization response on that session | That the account is demo unless account metadata is checked |
| Demo environment identified | Provider-returned account identity/type and endpoint/environment cross-check | That subsequent fills are complete or reconciled |
| Transaction observed | Provider transaction/fill identifier and raw response captured from the authenticated session | Completeness of the account ledger |
| Ledger reconciled | Pagination/sequence handling and comparison of transactions, fees, positions and balance | Independent provider attestation |
| Evidence accepted | Independent review of the source, implementation and threat model | Live-trading permission |

A local SHA-256 chain establishes tamper evidence relative to the local chain state. It does not independently authenticate the provider or the collector host.

## Required session lifecycle

1. Start in read-only mode. No order-capable adapter is constructed by default.
2. Load the API credential from a secret manager or process environment. Never accept it in chat, command-line arguments, URLs, repository files, test snapshots, exception text or logs.
3. Validate the configured endpoint against an exact allowlist. Reject live endpoints, unknown hosts, redirects, insecure transport, URL user-info, fragments and unexpected ports.
4. Establish TLS with certificate validation and hostname checking. Bind the session record to the observed socket and endpoint; caller-supplied booleans are not proof.
5. Send authorization and validate the provider response. Obtain account identity/type from provider-returned data, then enforce a demo-only allowlist. Missing, ambiguous, inconsistent or live account metadata must fail closed.
6. Keep the session read-only until an explicit operator action enables a demo session. That action must not bypass the shared execution service, risk engine, exposure reservations or emergency stop.
7. Persist a redacted session audit record: opaque session ID, endpoint identifier, account-ID fingerprint (not the raw account ID), account type, authorization time, protocol version and verifier version. Do not persist credentials or OTPs.
8. On disconnect, authorization expiry, account/environment mismatch, clock anomaly or failed reconciliation, disable order capability and require a fresh verified session.

## Evidence event contract

Each provider event admitted to the demo evidence ledger should include:

- Provider and environment labels, with environment obtained from authenticated provider account metadata.
- Stable provider transaction/fill ID and event type.
- Provider event timestamp and collector receive timestamp, both timezone-aware and normalized to UTC.
- Authenticated session ID and account fingerprint.
- Instrument/contract identity, side, quantity, price, currency, fees and realized result when supplied by the provider.
- Source response digest and schema version.
- Pagination cursor/sequence metadata where applicable.

Reject or quarantine events with missing stable IDs, conflicting duplicates, invalid chronology, unknown account/session, mismatched environment, malformed monetary values, or secret-like payload fields. Idempotency must be keyed by provider identity plus transaction ID; reuse with different content is a hard conflict.

Never synthesize missing fills, fees, positions, rejected orders, timestamps or slippage. Missing values remain explicitly unavailable. Reconciliation must account for pagination, partial fills, corrections, reversals, open contracts and final positions. A daily heartbeat is evidence of process continuity only; it is not a substitute for account-ledger reconciliation.

## Execution controls

- All order intents, buys, sells, cancellations and closes must pass through `core.execution.ExecutionService` and the existing risk/reservation path.
- The adapter must reject unsupported order types and instruments rather than silently translating them.
- Apply bounded stake/contract size, exposure caps, stale-quote checks, duplicate intent protection, request timeouts and safe reconnect behavior.
- A reconnect must re-authorize and re-check account identity before any order capability is restored.
- Keep the emergency stop and kill switch mandatory and operator-visible. No environment flag, API parameter or research module may disable them.
- The runtime must continue to reject `demo` and `live` modes until a separately reviewed enablement change exists. This design document grants no permission to submit even demo orders.

## Test and review matrix

Before implementation can be considered for merge, add deterministic mocked tests for:

1. Missing/invalid credential and authorization rejection, without leaking secrets.
2. Live endpoint, live account, ambiguous account type and endpoint/account mismatch.
3. TLS verification failure, hostname mismatch, disconnect and reconnect.
4. Duplicate event idempotency and same-ID/different-payload conflict.
5. Pagination gaps, repeated pages, out-of-order timestamps and event corrections.
6. Partial fills, fees, rejected orders, open positions and reconciliation mismatch.
7. Stale quote, risk rejection, exposure reservation failure and emergency stop.
8. Restart recovery and durable append-only ledger verification.
9. Confirmation that no event or heartbeat from mocks/fixtures can be counted as authenticated forward evidence.

The tests must assert that all failure paths leave order capability disabled. Mock tests validate software behavior only; they are not Deriv account authentication evidence.

## Staged acceptance

- **Stage A — offline protocol:** typed request/response parsing, strict endpoint/account validators, fake transport tests; no credentials and no network order path.
- **Stage B — read-only demo identity:** real authenticated demo authorization and account metadata verification, with redacted audit output; no order methods exposed.
- **Stage C — read-only account ledger:** retrieve and reconcile actual demo transactions, fills, fees and positions; no order methods exposed.
- **Stage D — controlled demo execution:** only after independent code/security review and explicit operator approval; every action still passes through the existing risk controls and emergency stop.
- **Certification:** Level 3's separate 30-consecutive-day evidence gate remains independent. A successful demo login, green CI, local hash chain or daily heartbeat does not satisfy it. Level 4 and live trading remain unavailable until their separate prerequisites and explicit approvals are met.

## Operational and cost constraints

No paid infrastructure may be provisioned under the current project authorization. Keep the design compatible with a maximum hosting budget of **₦5,000/month**, but do not claim a provider is affordable or suitable until current pricing, data-egress costs, uptime, persistence and secret-management capabilities have been verified. No deployment is part of this change.

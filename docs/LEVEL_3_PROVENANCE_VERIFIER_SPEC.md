# Level 3 provenance verifier — implementation and audit specification

**Status: design only; evidence credit remains blocked.** This document does not claim that Deriv signs public tick messages or that the current collector independently attests the TLS session.

## 1. Current verified behavior

The read-only collector connects to the fixed public Deriv WebSocket endpoint with certificate-chain and hostname verification requested from its WebSocket client. It retains the raw message, its SHA-256 digest, the normalized EURUSD tick, provider epoch, collector receive timestamp and endpoint string. The forward-evidence store independently enforces freshness, UTC-day accounting, duplicate handling and a hash chain.

The current collector's `tls_verified` argument is caller-supplied metadata. The stored `transport_security_claim` is therefore not proof that a particular socket completed authenticated TLS. The raw-message hash proves only that the stored bytes have not changed relative to that digest; it does not identify who sent them. The current binding validator is a consistency check, not provider authentication. The store correctly records these as unverified candidates and returns `BLOCKED_PROVENANCE`.

## 2. Trust decision required before evidence credit

Deriv's public tick messages are not documented here as individually signed. Do not invent a signature format, embed a test key, treat a caller boolean as proof, or infer provider authenticity from a self-reported endpoint string.

The proposed acceptable path for independent review is **authenticated transport provenance**:

1. The collector itself creates the connection to the fixed, allow-listed Deriv public WSS hostname. No externally supplied socket or proxy is accepted by default.
2. TLS certificate-chain validation and hostname verification are mandatory; certificate validation errors terminate the session. No insecure fallback, custom untrusted CA, disabled hostname check, or silent reconnect downgrade is permitted.
3. The verifier obtains evidence from the actual established TLS socket, not function arguments or JSONL fields: peer certificate DER and SHA-256 fingerprint, negotiated TLS version/cipher, verified peer hostname, and the configured trust-store identity/version. If the WebSocket library cannot expose these values reliably, replace or wrap the transport with a supported TLS API; do not introspect undocumented internals and call that audited.
4. The collector creates a unique session ID and records connection start/end, reconnect boundaries, endpoint, host clock status, monotonic receive sequence, UTC receive time and the TLS peer evidence. Every tick is bound to that active session and sequence.
5. The verifier parses the raw message itself and binds provider, instrument, resolved Deriv symbol, event epoch, quote, event identity, session ID and collector receive time. Caller-provided normalized fields are compared to parsed values, never trusted.
6. The store accepts a verified result only through a verifier object constructed inside the trusted collector process. A JSON/JSONL field, CLI flag, environment variable, database edit or arbitrary callback supplied by an importer must not enable verification.
7. Reconnects create new sessions and new peer evidence. Duplicate/replayed events, stale/future timestamps, symbol changes, malformed messages, endpoint changes, certificate failures and tampered payloads are rejected or retained as unverified candidates; they never increase the verified-day streak.
8. The database retains raw payload, payload digest, parsed fields, verifier version, session evidence, decision/reason, collector build commit and append-only audit-chain linkage. Restrict write access and preserve immutable backups.

**Important:** TLS authenticates the server endpoint for a transport session; it is not a Deriv digital signature over each tick and is not non-repudiation. Independent reviewers must explicitly decide whether this authenticated-channel evidence is sufficient for this programme. If not, keep the evidence gate blocked until Deriv or another authorized provider supplies signed messages or a separately trusted attestation mechanism.

## 3. Required implementation boundary

- Introduce a narrow provider verifier interface with an immutable verification result containing verifier ID/version, verified boolean, reason code, session ID and evidence digest.
- Only the live collector's internally established, successfully verified session can construct a trusted session context.
- The JSONL importer remains untrusted and cannot create verified observations.
- Remove any interpretation of `tls_verified` or `transport_security_claim` as proof. These may be retained only as diagnostic labels explicitly marked untrusted, or removed.
- Default behavior remains fail-closed: missing verifier, missing session evidence, unknown verifier version, or exception means unverified candidate and zero coverage credit.
- Do not turn on the evidence-credit path until tests, code review and an independent provenance review have all passed.

## 4. Acceptance tests

Required positive and negative tests:

- Real TLS integration test against a controlled local test server with a test CA: trusted CA + correct hostname succeeds; untrusted CA, expired certificate and hostname mismatch fail closed.
- A caller-supplied `tls_verified=true`, endpoint string, session ID or fabricated certificate fingerprint cannot produce verified evidence.
- A message delivered over an authenticated test session is bound to that session's actual peer evidence and sequence.
- Replayed event ID, duplicate sequence, stale event, future event, wrong symbol/instrument, malformed tick and reconnect/session mismatch do not receive evidence credit.
- Mutating raw bytes, normalized price, event epoch, instrument, provider, session metadata or certificate evidence invalidates verification.
- JSONL import, direct store API calls and database rows cannot set `provenance_verified=1` without the trusted verifier path.
- Restart preserves the audit chain and verifier/session provenance; tampering is detected and the collector fails closed.
- No test fixture, mock verifier, historical replay or CI run is represented as a live provider observation.

## 5. Independent review checklist

Reviewer must be independent of the implementation author and record identity, date, commit SHA, scope and explicit approval/rejection for:

- Deriv endpoint ownership and applicable public data terms.
- TLS hostname/chain verification and actual socket evidence capture.
- Trust-store provenance, certificate rotation and failure behavior.
- Raw payload-to-normalized-field binding and replay handling.
- Trusted-code boundary preventing caller/importer bypass.
- Clock synchronization, timestamp semantics and UTC day accounting.
- Storage permissions, retention, backup integrity and audit-chain recovery.
- The precise claim being accepted: authenticated transport provenance, not provider-signed ticks or non-repudiation.

No reviewer approval means no evidence-credit enablement.

## 6. Level 3 gate

Until the above is implemented and independently approved:

- evidence status remains `BLOCKED_PROVENANCE`;
- verified forward-observation days remain zero;
- the 30-day clock has not started;
- CI, synthetic cycles, historical replay and unverified live candidates do not count;
- Level 3 is not certified.

The collector remains public read-only market-data only. Broker adapters stay disabled, the paper kill switch stays engaged, and no account authentication or trade execution is permitted.

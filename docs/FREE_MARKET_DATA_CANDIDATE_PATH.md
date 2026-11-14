# Free Market-Data Candidate Path (EURUSD)

## Decision summary

Jarvis Unified will use a zero-subscription-cost path for development and candidate-only paper observation while preserving the Option C provenance requirement.

**No currently reviewed free source qualifies for verified Level 3 evidence.** A free quote API, HTTPS/TLS connection, payload hash, checksum, sequence number, or local timestamp is not by itself proof that an individual tick originated from the claimed market-data source.

Current gate: `BLOCKED_PROVENANCE`.
Verified forward days: `0`.
30-day clock: not started.
Live execution: disabled; paper kill switch engaged.

## Free-source assessment (research only)

| Source | Potential use | Limitations / status |
|---|---|---|
| Biquote public API/WebSocket | Optional live quote candidate for schema, freshness, reconnect and pipeline testing | Public documentation advertises anonymous live REST/WebSocket access and multi-source aggregation. No per-tick signature or contractual audit guarantee has been established. Candidate-only; do not award evidence credit. |
| FXCM public historical tick archive | Offline historical parser/backtest fixtures if licence permits | FXCM describes the data as indicative, timestamps UTC, and personal-use under its EULA. Do not use for commercial/redistributed datasets or automated ingestion until legal terms are checked and permission is confirmed. Not forward evidence. |
| Dukascopy historical export / dukascopy-node | Offline historical research only after terms review | Third-party downloader is not a Dukascopy authenticity attestation. Dukascopy website terms may restrict automated scraping, database construction and use beyond personal non-commercial purposes. Do not automate downloads or store/redistribute data until written permission and current terms are reviewed. |
| Deriv public WSS | Existing transport candidate and comparison feed | Keep candidate-only. TLS/session binding does not authenticate individual ticks. |
| TickDataFeed | Future paid evaluation only | Published FX + Crypto plan is paid; not in the zero-cost path. Published checksums and sequence-checked delivery still require exact signature/audit assurance review. |

This is a technical triage, not legal advice or a vendor endorsement. Re-check current terms before any ingestion.

## Adapter contract

Any free-source integration must be isolated behind a provider adapter and must emit a normalized observation plus immutable provenance metadata:

- provider identifier and endpoint/product identifier;
- exact instrument identity and instrument type (spot FX, CFD, futures must not be conflated);
- raw provider message bytes or an immutable reference to access-controlled raw storage;
- provider event ID / sequence if supplied;
- provider event timestamp and local UTC receive timestamp, kept separately;
- bid/ask/mid as actually supplied; never synthesize a bid/ask pair from mid;
- raw payload SHA-256 for integrity/deduplication only;
- transport/session metadata separately from provider authenticity;
- explicit trust classification: `candidate_unverified`, `historical_research_only`, or a future provider-specific verified status.

For the free candidate path, the adapter must hard-code `evidence_credit=false` at the trust boundary. It must not accept caller-supplied `verified`, `provenance_verified`, `tls_verified`, or similar booleans as authority. JSONL import, replay, mocks, checksums and tests must never upgrade trust.

## Required controls and tests before a free candidate collector is enabled

1. Confirm the provider's current terms allow the intended automated access, local retention, research and storage.
2. Verify symbol mapping and exact instrument/source semantics.
3. Validate timestamps, monotonicity, duplicate/replayed messages, gaps, out-of-order data, stale data and reconnect behavior.
4. Preserve original raw messages and hash them; clearly label the hash as integrity evidence, not origin authentication.
5. Bound storage, rotate sessions safely and prevent overlapping SQLite writers.
6. Add tests for malformed payloads, wrong symbol, stale event time, replay, gaps, reconnect, duplicate IDs, clock skew and tampering.
7. Confirm the provenance gate remains blocked and the verified-day count remains zero for all candidate observations.

## Option C verification acceptance (unchanged)

A provider can only be considered for Level 3 evidence after Jarvis obtains technical documentation and written contractual confirmation for one of:

- cryptographic per-message signatures with documented algorithm, canonicalization, public-key distribution/rotation, revocation and verification procedure; or
- a contractually auditable source trail with immutable event IDs, documented source lineage, retention, correction policy and an audit process independently reviewable by Jarvis.

A file checksum only proves that a file has not changed relative to a trusted checksum source; it does not prove the underlying tick's origin. TLS authenticates a connection endpoint, not each individual message after ingestion.

Before evidence credit: implement provider-specific verification; test positive, invalid signature, tampering, replay, stale, wrong instrument, key rotation/revocation and raw-payload binding; retain raw artifacts; obtain independent technical review; obtain explicit owner approval for the selected provider and any paid commitment.

## Current next steps

- [ ] Request written technical and licence answers from free candidate provider(s), without creating an account or agreeing to terms on the owner's behalf.
- [ ] If Biquote is used for pipeline testing, isolate it as candidate-only and verify current terms, EURUSD instrument identity, source metadata, timestamp semantics and stability first.
- [ ] Do not automatically scrape FXCM or Dukascopy historical data until permissions and terms are resolved.
- [ ] Build candidate adapter and adversarial tests only after the existing collector interfaces and storage schema are reviewed against this contract.
- [ ] Keep the 30-day evidence clock stopped until the signed/auditable provider path and operational controls pass independent review.

## References

- FXCM historical tick archive: https://github.com/fxcm/MarketData/blob/master/TickData/README.md
- Biquote API overview: https://biquote.io/
- Biquote API docs: https://biquote.io/docs/
- Dukascopy-node documentation: https://www.dukascopy-node.app/
- TickDataFeed pricing and delivery claims: https://tickdatafeed.com/pricing.php

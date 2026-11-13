# Provenance trust model — Issue #9

**Status:** design + fail-closed implementation on `main`.  
**Evidence credit:** **disabled**. All forward observations remain **unverified candidates** until independent review accepts a trust boundary and an implementation that cannot be bypassed.

## 1. Goal

Define what Jarvis can honestly claim about market-data observations from the **Deriv public EUR/USD WebSocket**, and enforce that stronger claims cannot be manufactured in software.

## 2. Threat model

| Threat | Mitigation today | Residual risk |
|--------|------------------|---------------|
| Caller injects `provenance_verifier=lambda: True` | Constructor rejects; verified always `False` in store | None for this vector |
| JSON field `provenance_verified: true` on ingest | Store ignores; forces `False` | None for this vector |
| Legacy DB with verified=1 rows | Open fails; require new DB | Operator must archive old DB |
| Caller-supplied `tls_verified=True` | Removed; claim is always `unverified` | None for this vector |
| Stale / future / backfilled timestamps | Age gates on collector clock | Compromised host clock |
| Tampered raw message after receipt | SHA-256 of raw payload + binding checks | Attack on disk after write |
| MITM on public WSS | `CERT_REQUIRED` + hostname check in collector | Trust in CA store / pinned endpoint only |
| **Provider forges or substitutes ticks** | **Not mitigated** — no per-tick signature | **Accepted residual** |
| **Replay of captured ticks as “live”** | Freshness window (10 min) | Replay within window still possible |

## 3. What the Deriv public feed can prove

Per Deriv’s public tick interface (as used by `research/deriv_feed.py`):

- Messages are **not documented as individually signed**.
- TLS + hostname verification can support a claim that the collector **opened a TLS session** to the **pinned hostname** (`api.derivws.com`) using the system trust store.
- That is **not** equivalent to:
  - a cryptographic signature over each tick,
  - non-repudiation by Deriv,
  - proof that a third party did not operate a malicious endpoint with a valid cert under some CA failure scenario,
  - proof of economic truth of the quote.

**Honest claim ceiling for this feed:**

> “Collector process C, at time T, received message M over a TLS connection whose peer hostname matched the pinned Deriv public endpoint, and stored M with hash H and binding checks B.”

Anything stronger is **out of scope** for the public tick feed and must not be encoded as `provenance_verified=1`.

## 4. Accepted trust boundary (proposal for independent review)

Until review accepts otherwise:

1. **Default and only production path:** store observations as `unverified_candidate`; gate remains `BLOCKED_PROVENANCE`.
2. **Transport session record** (optional, informational): capture endpoint URL, collector git identity if provided, process start UTC, and that certificate verification was requested. Never alone promotes a row to verified.
3. **Promotion to verified** requires a **separate, reviewed module** that:
   - is not a caller-supplied callback,
   - is not driven by JSON/CLI flags,
   - documents the exact cryptographic or contractual basis,
   - is named and versioned in metadata,
   - has adversarial tests (forged payload, replay, wrong instrument, tamper).
4. If no such module can exist for public ticks, Level 3 either:
   - uses a **different provider** with signed ticks, or
   - adopts an **explicit policy exception** (written, reviewed) that Level 3 evidence may rest on the weaker TLS+binding ceiling — **never silent**.

## 5. Socket-to-ledger path (current design)

```text
Pinned WSS endpoint
    → TLS CERT_REQUIRED + check_hostname
    → raw recv bytes
    → build_tick_observation (parse, bind symbol/epoch/quote)
    → transport_security_claim = "unverified"
    → ForwardEvidenceStore.ingest
         → freshness vs collector clock
         → provenance_verified = False  (hard-coded)
         → SHA-256 hash chain append (BEGIN IMMEDIATE)
```

Local binding (`validate_deriv_observation_binding`) proves **payload consistency**, not provider authenticity.

## 6. Independent review checklist

- [ ] Threat model above accepted or amended in writing
- [ ] Confirm no path sets `provenance_verified=1` without reviewed module
- [ ] Confirm public Deriv ticks are correctly described as unsigned
- [ ] Decide: alternate provider vs explicit weaker policy vs hold Level 3
- [ ] Host integrity (#11) in scope for clock and disk threats

## 7. Non-goals

- Live trading or account authentication
- Manufacturing verified evidence to force a 30-day gate PASS
- Claiming Level 3 from TLS alone

Paper-only. Kill switch remains engaged for trading paths.

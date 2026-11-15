# Issue #9 — provenance policy-exception proposal

**Status: PROPOSED. Not accepted. Evidence credit remains disabled and the verified-day count remains 0.**
Date: 2026-11-15. Decision owner: repository owner. An independent reviewer (not the implementer) must sign off.

This document prepares the decision that `docs/PROVENANCE_TRUST_MODEL.md` section 4.4 already allows: either use a
provider with signed ticks, or adopt an **explicit, written, reviewed** exception that Level 3 evidence may rest on a
weaker ceiling. It does not accept the exception, implement a verifier, or change any gate.

## 1. The decision

Which path should the first Level 3 evidence run use?

| Path | What it gives | Cost and time | Main limit |
|---|---|---|---|
| **P1. Signed-provenance provider** | Per-message signatures or a contractual audit trail (Option C in `FREE_MARKET_DATA_CANDIDATE_PATH.md`) | Paid plan, vendor diligence, a provider-specific verifier plus independent review. No vendor has passed (`EURUSD_PROVIDER_ASSURANCE_REVIEW_2026-11-14.md`). | Slow. Weeks of diligence before day 1, and a spending decision. |
| **P2. Policy exception (TLS-ceiling)** | Evidence on the Deriv public feed, labelled with its true ceiling | No cost. Needs the reviewed verifier module described in section 3. | Cannot detect a provider that forges or substitutes ticks. |
| P3. Wait | Nothing | Nothing | Clock never starts. |

P1 and P2 are not exclusive: P2 can start the clock now while P1 diligence continues.

## 2. What the exception would and would not claim

Honest claim ceiling (from the trust model, unchanged):

> Collector process C, at time T, received message M over a TLS connection whose peer hostname matched the pinned
> Deriv public endpoint, and stored M with hash H and binding checks B.

It would **not** claim: that ticks are signed, that Deriv cannot repudiate them, or that the quotes are the economic
truth. Any report built on P2 evidence must say so in its first paragraph and carry the label **`L3-TLS-CEILING`** so it
cannot be mistaken for signed-provenance Level 3.

Residual risks the owner would be accepting (all already listed in the trust model threat table):

| Risk | Status under P2 |
|---|---|
| Provider forges or substitutes ticks | Not mitigated. Accepted residual. |
| Replay of captured ticks inside the freshness window | Possible within 10 minutes. Mitigated only by the freshness gate. |
| CA failure or malicious endpoint with a valid certificate | Not mitigated beyond hostname pinning. |
| Compromised host clock | Not mitigated. Monitored (see compensating controls). |

## 3. Conditions that must hold before any row is marked verified

From trust model section 4.3. A promotion module must be a separate, reviewed module; not a caller callback; not
driven by JSON or CLI flags; named and versioned in row metadata; and covered by adversarial tests (forged payload,
replay, wrong instrument, tampered record). Specific to P2:

1. The module runs **inside the collector**, observing the real established `ssl.SSLSocket`. It must not trust the
   session record stored in row metadata, which the trust model notes is caller-writable.
2. Verified status records its basis explicitly (for example `basis = tls_pinned_host_v1`) and the evidence label
   `L3-TLS-CEILING`, so a later signed-provenance upgrade is distinguishable.
3. The existing guards stay: freshness window, hash chain, no backfill, one database per configuration.

## 4. Proposed compensating controls (owner to accept or amend)

- **Second-source cross-check.** Run the Biquote candidate collector in parallel (separate database, never credited).
  Compare it with the Deriv stream offline each day and record divergences beyond a tolerance. An undetected forgery
  would have to fool two independent feeds. This needs a small read-only comparison script (follow-up work).
- **Raw payload retention** and daily operator record exactly as in the persistent runner runbook, section 6.
- **Clock monitoring** with an alert on drift; a drifting clock voids the day.
- **No upgrade path to live use on this ceiling.** Proposed rule: Level 4 gating requires P1 (signed or contractually
  auditable provenance), regardless of Level 3 label. Live trading stays locked either way.

## 5. Recommendation (for the owner to weigh, not a decision)

Adopt P2 for the first certification pass with the controls in section 4 and the `L3-TLS-CEILING` label, and run P1
diligence in parallel so that Level 4 is not blocked by this choice. The reason is practical: it is the only path that can
start collecting without spending money or waiting on vendors, and the weaker ceiling is stated in the label instead of
hidden.

This is independent of the streak-definition problem in `LEVEL_3_TRADING_CALENDAR_PROPOSAL.md`. Even with P2 accepted,
the day count cannot reach 30 for EURUSD until that is decided too.

## 6. Decision record

| Decision | Choice | Name | Date |
|---|---|---|---|
| Path (P1 / P2 / P3) | | | |
| Compensating controls accepted | | | |
| Level 4 requires signed provenance | | | |
| Independent reviewer sign-off | | | |

Nothing here authorizes contacting vendors, opening accounts, accepting terms or spending money.

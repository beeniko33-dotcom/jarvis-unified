# UTC demo evidence continuity

`research.demo_evidence_continuity` is a deterministic policy helper for a future authenticated demo-evidence ingestion service.

- A day counts only when an explicit heartbeat event exists for that UTC calendar day.
- The current streak is counted backwards from the supplied `as_of_utc_day`.
- Any missing day breaks the streak; days are never interpolated.
- Duplicate days, duplicate heartbeat event IDs, non-canonical dates, and future-dated events are rejected.
- An absent heartbeat on the as-of day produces a zero-day current streak.

## Trust boundary

This helper performs continuity arithmetic only. It does not verify a Deriv account, authenticate provider-origin events, validate signatures, reconcile balances or positions, or make the 30-day gate eligible. The report deliberately returns `CONTINUITY_ONLY_NOT_AUTHENTICATED`, `provider_authenticity_verified=0`, and `evidence_eligible=false`. A trusted ingestion layer must verify source authenticity and ledger integrity before supplying records.

## Tests

`python -m unittest discover -s tests -p 'test_demo_evidence_continuity.py' -v`


The continuity assessor is intentionally not wired into live-readiness approval until authenticated account reconciliation and independent provider verification exist.

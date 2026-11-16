# Typed research event lineage

The research pipeline now has a typed event contract with five stages:

1. **Observation** — source-referenced raw market observation.
2. **Feature** — a derived feature linked to exactly one observation.
3. **Forecast** — a forecast linked to exactly one feature record.
4. **Decision** — a research decision linked to exactly one forecast.
5. **Outcome** — a realized or otherwise recorded outcome linked to exactly one decision.

## Integrity and chronology

- Events are append-only in SQLite and chained with SHA-256 hashes.
- Repeating an identical event ID and payload is idempotent; reusing an ID for changed content is rejected.
- Every non-observation stage requires one existing parent of the immediately preceding stage.
- Child timestamps cannot precede their parent timestamps.
- Timestamps must be timezone-aware and are normalized to UTC.
- Secret-like payload keys are rejected to keep credentials out of research records.
- Schema version is stored with each event.

## Trust boundary

A valid local hash chain demonstrates local record integrity only. It does **not** prove that a market-data provider originated the observation, that a demo broker account supplied an outcome, or that any event is eligible for the 30-day evidence gate. The report always states zero provider-authenticated events and `RESEARCH_ONLY`.

This module does not connect to a broker, place orders, change risk settings, promote strategies, or enable live trading.

## Tests

`python -m unittest discover -s tests -p 'test_research_event_lineage.py' -v`

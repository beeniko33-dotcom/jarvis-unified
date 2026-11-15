# Research source-health diagnostics

The research.source_health module adds deterministic cadence and outage diagnostics
for already-ingested observations.

## What it reports
- Observation count and duplicate, out-of-order, stale and clock-skew flags.
- Missing expected intervals between unique event timestamps.
- Age of the most recent event and an outage-suspected indicator.
- NO_DATA, OUTAGE_SUSPECTED, GAPS_DETECTED or CADENCE_OBSERVED status.

## Important limits
- Expected cadence is configuration, not a guarantee that a provider must publish in every interval.
- Gap counts are diagnostic estimates, not proof of provider failure.
- Reports are not provider authentication, source verification or Level 3 evidence.
- Every report remains candidate_unverified and evidence_eligible=false.
- No broker, account, order or network functionality is present.

## Tests
Run: python -m unittest discover -s tests -p test_research_source_health.py -v

# Research evidence pipeline (initial foundation)

This module is read-only market-observation intake. It does not generate trade orders, connect to accounts, or establish predictive edge.

## Guarantees
- Observation identity is a deterministic SHA-256 over canonical source, event time, instrument, timeframe, schema version and values.
- Duplicate content is rejected by a durable SQLite uniqueness constraint.
- Out-of-order, stale and future-clock-skew observations are retained with explicit quality flags rather than silently normalized.
- Every observation is hard-labelled `candidate_unverified`. The API exposes no caller-supplied verification boolean or evidence-credit override.
- Reports always show zero verified observations and `INSUFFICIENT_EVIDENCE` until a separately reviewed provider verifier is implemented.
- Forecast decision timestamps must precede the complete outcome window to prevent temporal leakage.

## Not implemented
Provider signatures, independent provenance verification, normalized features, opportunity ranking, forecast calibration, outcome attribution, baseline comparison and strategy promotion are deliberately separate follow-up work. This foundation cannot certify source authenticity or feed execution.

## Tests
`python -m unittest discover -s tests -p 'test_research_evidence_pipeline.py' -v`

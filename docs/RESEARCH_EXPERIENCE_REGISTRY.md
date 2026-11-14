# Research experience registry

The local SQLite experience registry stores versioned experiment metadata and outcome
summaries without modifying the paper execution ledger. Each experiment records a
hypothesis, strategy version, canonical configuration hash, dataset identifier and
hash, explicit dataset provenance label, chronological time range, metrics and
metrics hash. Records are append-only through this API.

Use `chronological_split` for ordered observations. It rejects shuffled timestamps
and creates non-overlapping train, validation and test index ranges. It never
randomly shuffles market observations.

This is research bookkeeping and split logic only. It does not run strategies,
calculate performance from raw fills, validate provider authenticity, prove
profitability, or promote a strategy. Synthetic and historical datasets remain
separately queryable and retain their provenance label.

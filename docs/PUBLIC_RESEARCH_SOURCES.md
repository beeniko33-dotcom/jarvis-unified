# Public research source adapters

## Scope
This module provides a small explicit source allowlist and a local historical OHLCV CSV importer. It is read-only and cannot connect to a broker, read account balances, submit orders or promote strategies.

## Frankfurter daily reference rates
- The adapter makes a request only when `fetch_frankfurter_daily(...)` is explicitly called.
- HTTPS host is fixed to `api.frankfurter.dev`; redirects to other hosts fail closed.
- Response size and timeout are bounded; currency codes and returned date are checked.
- Rates are daily reference values, not live prices, executable quotes or intraday candles.
- Review current provider terms and attribution requirements before redistribution or commercial use.

## Historical OHLCV CSV
- Reads only a local file supplied by the caller; it does not crawl or download files.
- Required columns: `timestamp,open,high,low,close`; optional `volume`.
- Timestamps must be ISO-8601 with an explicit timezone.
- OHLC relationships, positive finite prices and non-negative finite volume are validated.
- The parser cannot establish the file's publisher, authenticity or licence. Such rows remain candidate_unverified.

## Provenance
The adapter writes source URL, publisher, terms URL, retrieval timestamp, data class and licence-status notes to a separate SQLite sidecar keyed by the observation content hash. Unknown rights remain explicitly unknown. The evidence pipeline still hard-labels all observations candidate_unverified; verified count remains zero.

## Example (explicit invocation only)
```python
from datetime import date
from research.evidence_pipeline import ResearchEvidencePipeline
from research.public_sources import fetch_frankfurter_daily, ingest_public_records

pipeline = ResearchEvidencePipeline("data/research.sqlite")
record = fetch_frankfurter_daily(date(2026, 11, 13), base="EUR", quote="USD")
result = ingest_public_records(
    [record], pipeline=pipeline,
    provenance_database="data/source_provenance.sqlite",
)
print(result)
```

Do not use daily reference rates for execution simulation. Use broker-specific historical quotes/ticks for execution-quality research. No automated scheduler or persistent worker is included.

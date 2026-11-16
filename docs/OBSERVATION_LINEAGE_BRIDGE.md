# Execution observation to research lineage bridge

## Purpose

The bridge copies the append-only execution observation journal into the typed
research event ledger. It is an explicit, read-only import step; it does not
change execution, broker adapters, risk controls, or strategy behavior.

## Mapping

Each source journal event becomes one root observation event with a stable
execution-observation-prefixed identity. The copied payload retains the source
event ID, event type, sequence, schema version, source event hash, and original
data. Imports are idempotent and paginated.

Only observation nodes are created. The importer does not invent feature,
forecast, decision, or outcome stages. Those stages require their own producers
and must reference the correct immediate parent under the typed ledger rules.

## Integrity and provenance boundary

- The source hash chain is verified before and after import.
- The destination lineage chain is verified before and after import.
- A source event hash is retained as a local integrity reference.
- Local hashes do not prove source origin, provider authenticity, or broker account identity.
- Imported records are explicitly labelled as paper execution observations.
- The report always states provider authenticity verified is zero,
  evidence eligibility is false, and status is research only.
- Secret-like payload keys are rejected by the typed ledger; the importer does
  not strip or silently redact them.

This is a local research lineage feature only. It does not make paper data
eligible for the 30-day authenticated Deriv demo evidence gate.

# Research integrity is not provenance verification

## Security correction

A local SHA-256 match between an experiment's recorded ledger/journal hashes and the current local files proves byte-for-byte integrity relative to those recorded hashes. It does **not** prove who produced the data, whether the original market feed was authentic, or whether the source was independently audited.

Jarvis therefore records this result as `integrity_matched_unverified`. It is not eligible for evidence-based experiment comparison, forward-validation credit, strategy promotion, or Level 3 certification.

## Migration behavior

Older versions of the experiment registry used the label `verified` for matching local file hashes. On opening an existing registry, the schema migration downgrades those historical records to `integrity_matched_unverified`. This is intentionally conservative: previously stored labels cannot be assumed to have stronger provenance than the mechanism that created them.

A hash mismatch remains `mismatch` and blocks comparison.

## What would be required for independent verification

A future provider-specific verifier must be implemented only after a provider and its exact instrument/feed have been approved. It must authenticate the original provider payload or an equivalent independently controlled attestation, bind the authenticated data to instrument, event identity, event time and values, and validate key/credential lifecycle and replay behavior. Positive and adversarial tests plus independent review are required.

A caller-supplied boolean, local file hash, mocked verifier, historical CSV, RSS headline, chart screenshot or replay fixture cannot grant verified status.

## Current operation

- Market observations remain `candidate_unverified`.
- Experiment artifacts may be integrity-checked, but not independently provenance-verified.
- Innovation Lab results remain advisory and non-executing.
- No broker/account/order access is introduced by this boundary.
- Paper-only controls and the emergency stop remain in force.

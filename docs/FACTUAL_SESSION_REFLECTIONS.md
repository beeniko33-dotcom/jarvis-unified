# Factual session reflections

`ReflectionStore` builds a persistent reflection snapshot from caller-supplied
`SessionEvent` records. Every fact retains its source reference, timestamp, event
type and provenance label. Owner corrections are listed separately. Repeated event
types can produce a clearly labelled hypothesis; they are never presented as proof
of improved trading performance.

The builder does not call an LLM, inspect external accounts, infer market outcomes,
or change strategy/risk settings. Missing information is recorded under unknowns,
and next steps are low-risk review suggestions. Reflections live in a separate
SQLite database and do not write to the paper execution or audit ledger.

# Signals

Signal generation produces `SignalIntent` objects only. Conversion to `OrderRequest` and submission happens exclusively through `core.execution.ExecutionService` so the central risk gate cannot be bypassed.

Concrete strategy modules will be migrated selectively from `jarvis-trader` / `quantum-peak-pro` after inventory.

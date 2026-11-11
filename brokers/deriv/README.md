# Deriv adapter

Skeleton only. Construction raises `RuntimeError` so the adapter cannot be used accidentally.

When implemented:
- Talk exclusively through the shared `Broker` protocol
- All orders must enter via `core.execution.ExecutionService`
- Demo first; live requires Level 4 gates and human approval
- Source logic may be ported from `jarvis-ai-trading-system` after inventory

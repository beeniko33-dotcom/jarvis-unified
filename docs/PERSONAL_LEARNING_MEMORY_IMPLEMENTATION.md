# Personal learning memory — first implementation slice

The first code slice provides a local SQLite-backed store for personal preferences and tentative learning candidates.

## Use

```python
from core.learning.memory_store import MemoryStore

memory = MemoryStore("var/jarvis_learning.sqlite3")
memory.put("communication", "detail", "Concise by default")
memory.put(
    "workflow", "daily_report", "Include risks and unresolved blockers",
    source="explicit_user_feedback",
)
for item in memory.list_memories():
    print(item.category, item.memory_key, item.content, item.source, item.confidence)

print(memory.export_json())
memory.delete("communication", "detail")
```

Allowed sources:
- `explicit_user_feedback`: confidence is fixed at 1.0 and takes precedence over weaker sources.
- `repeated_choice`: default confidence 0.7.
- `inferred_candidate`: default confidence 0.4 and cannot overwrite explicit feedback.

The store uses SQLite WAL and FULL synchronous durability. It is separate from trading ledgers and risk configuration. Its event history records create/update/delete metadata without copying memory content into the event log. Deleting a memory removes its content from the active memory table; it does not promise forensic erasure from filesystem snapshots or backups.

This slice does not infer preferences automatically, call an LLM, alter strategy parameters, connect to brokers, or execute trades. It is a persistence foundation for subsequent preference capture, reflection, and research learning.

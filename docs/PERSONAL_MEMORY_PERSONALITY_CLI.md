# Personal memory and personality CLI

Jarvis can now manage personal preferences locally without exposing a write API.

```bash
# Save an explicit preference
python main.py --remember communication report_style "Concise daily reports"

# Inspect saved memories
python main.py --memory-list

# Build personality context from saved preferences
python main.py --personality-context

# Delete a preference
python main.py --forget communication report_style
```

The default store is `var/learning/memory.sqlite3`; override it with
`--memory-db /path/to/memory.sqlite3`.

The personality context is a reusable text profile for an AI integration. The current
Python runtime does not itself host or call an LLM, so this CLI does not claim that
Jarvis is already autonomously conversing or learning from every interaction.
Preferences are only saved when explicitly supplied through the CLI or another
trusted integration. Inferred preferences remain labelled candidates. The context
is explicitly subordinate to risk, provenance, privacy and approval controls.

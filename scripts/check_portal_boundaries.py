"""Guard the static public portal against legacy execution-oriented UI."""
from pathlib import Path

PORTAL = Path("apps/portal/index.html")
source = PORTAL.read_text(encoding="utf-8").lower()

required = (
    "forex signal intelligence",
    "marketplace",
    "career",
    "jaeo",
    "read-only market observations",
    "not trade instructions",
    "under active development",
)
for phrase in required:
    if phrase not in source:
        raise SystemExit(f"public portal is missing required product-boundary text: {phrase}")

forbidden = (
    "paper trading",
    "paper environment",
    "simulated orders",
    "place orders",
    "broker execution",
    "execution adapter",
)
for phrase in forbidden:
    if phrase in source:
        raise SystemExit(f"public portal contains forbidden legacy execution language: {phrase}")

print("public portal product boundaries verified")

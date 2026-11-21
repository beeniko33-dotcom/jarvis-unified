"""Guard public Jarvis entry points against legacy execution-oriented UI."""
from pathlib import Path
import re

PORTAL = Path("apps/portal/index.html")
CONTROL_PANEL = Path("apps/control_panel/index.html")

portal_source = PORTAL.read_text(encoding="utf-8").lower()
control_source = CONTROL_PANEL.read_text(encoding="utf-8").lower()

portal_required = (
    "forex signal intelligence",
    "marketplace",
    "career",
    "jaeo",
    "read-only market observations",
    "not trade instructions",
    "under active development",
)
for phrase in portal_required:
    if phrase not in portal_source:
        raise SystemExit(f"public portal is missing required product-boundary text: {phrase}")

portal_forbidden = (
    "paper trading",
    "paper environment",
    "simulated orders",
    "place orders",
    "broker execution",
    "execution adapter",
)
for phrase in portal_forbidden:
    if phrase in portal_source:
        raise SystemExit(f"public portal contains forbidden legacy execution language: {phrase}")

workspace_required = (
    "forex signal intelligence",
    "career giver",
    "marketplace",
    "jaeo",
    "read-only research",
    "order intents",
    "do not execute actions",
    "./career.html",
    "./marketplace.html",
    "https://jarvis-unified-portal.pages.dev/jaeo.html",
    "getregistrations()",
    "registration.unregister()",
    "caches.delete(key)",
)
for phrase in workspace_required:
    if phrase not in control_source:
        raise SystemExit(f"public workspace is missing required product-boundary text: {phrase}")

workspace_forbidden = (
    "paper trading",
    "paper environment",
    "simulated orders",
    "run_paper_session",
    "broker execution",
    "place orders",
    "kill switch",
    "open positions",
    "live brokerage",
)
for phrase in workspace_forbidden:
    if re.search(rf"\b{re.escape(phrase)}\b", control_source):
        raise SystemExit(f"public workspace contains forbidden legacy execution language: {phrase}")

print("public portal and workspace product boundaries verified")

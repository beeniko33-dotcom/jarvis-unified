"""Static and JavaScript smoke checks for the hosted Jarvis control panel."""
from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "apps" / "control_panel" / "index.html"


class PanelParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.pages: set[str] = set()
        self.route_links: set[str] = set()
        self.module_script: list[str] = []
        self._in_module = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.add(values["id"] or "")
        if values.get("data-page"):
            self.pages.add(values["data-page"] or "")
        if values.get("data-route-link"):
            self.route_links.add(values["data-route-link"] or "")
        if tag == "script" and values.get("type") == "module":
            self._in_module = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._in_module:
            self._in_module = False

    def handle_data(self, data: str) -> None:
        if self._in_module:
            self.module_script.append(data)


def main() -> int:
    source = PANEL.read_text(encoding="utf-8")
    parser = PanelParser()
    parser.feed(source)
    required = {
        "signin", "auth-form", "auth-email", "auth-password", "toggle-password",
        "page-chart", "page-forecast", "candle-canvas", "rsi-canvas",
        "chart-symbol", "chart-provider", "markets-provider", "market-search", "market-pairs-body",
        "market-pair-count", "forecast-symbol", "signal-direction",
    }
    missing = sorted(required - parser.ids)
    if missing:
        raise SystemExit("Missing control-panel elements: " + ", ".join(missing))
    if not parser.pages.issubset({p.removeprefix("page-") for p in parser.ids if p.startswith("page-")}):
        raise SystemExit("A navigation destination has no matching page panel")
    if not parser.route_links.issubset(parser.pages):
        raise SystemExit("A page link targets an unknown route")
    if "prefers-color-scheme" not in source or "prefers-reduced-motion" not in source:
        raise SystemExit("Browser accessibility and display preferences are not respected")
    for feature in ("loadPairUniverse", "/spot/currency_pairs", "/spot/tickers",
                    "/v5/market/instruments-info?category=spot", "/v5/market/tickers?category=spot",
                    "history.replaceState({page:", "fitWorkspaceLayout", "ResizeObserver",
                    "market-open-chart"):
        if feature not in source:
            raise SystemExit("Missing adaptive/auth/market-universe feature: " + feature)
    if "document.documentElement.style.zoom" in source or "document.body.style.zoom" in source:
        raise SystemExit("Workspace must reflow without overriding browser zoom")
    module = "".join(parser.module_script)
    if not module.strip():
        raise SystemExit("No application module script was found")
    result = subprocess.run(
        ["node", "--check", "--input-type=module"],
        input=module,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        sys.stderr.write(result.stderr)
        raise SystemExit("Control-panel JavaScript syntax check failed")
    manifest = (ROOT / "apps" / "control_panel" / "manifest.webmanifest").read_text(encoding="utf-8")
    worker = (ROOT / "apps" / "control_panel" / "service-worker.js").read_text(encoding="utf-8")
    if '"orientation": "any"' not in manifest or "jarvis-control-shell-v3" not in worker:
        raise SystemExit("Installed app manifest/cache version is not updated")
    print("Control panel pages, responsive preferences, PWA shell and JavaScript syntax: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

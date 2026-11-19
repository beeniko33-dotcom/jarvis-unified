"""Smoke-test the isolated Cloudflare Worker Preview created for PR #204."""
import json
from urllib.request import Request, urlopen

PREVIEW_URL = (
    "https://engineering-gateio-attestation-verifier-2-jarvis-control-worker."
    "beeniko33.workers.dev/health"
)
EXPECTED_HOST = "engineering-gateio-attestation-verifier-2-jarvis-control-worker.beeniko33.workers.dev"


def main() -> int:
    request = Request(PREVIEW_URL, headers={"Accept": "application/json"})
    with urlopen(request, timeout=15) as response:
        if response.status != 200 or response.geturl().split("/")[2] != EXPECTED_HOST:
            raise RuntimeError("Cloudflare Worker Preview health endpoint failed")
        body = response.read(16_385)
    if len(body) > 16_384:
        raise RuntimeError("Preview health response exceeded size limit")
    payload = json.loads(body)
    assert payload.get("mode") == "paper"
    assert payload.get("live_trading") == "disabled_by_design"
    assert payload.get("paper_session_execution") == "disabled_pending_postgres_migration"
    print(json.dumps({
        "ok": True,
        "preview": EXPECTED_HOST,
        "mode": payload["mode"],
        "live_trading": payload["live_trading"],
        "paper_session_execution": payload["paper_session_execution"],
        "ingest_token_configured": payload.get("ingest_token_configured"),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

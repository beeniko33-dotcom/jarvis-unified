"""Live smoke test for the isolated Cloudflare Gate.io attestor.

Fetches public market data through the verifier endpoint and verifies its Ed25519
signature with the repository-pinned public key. Never writes to Supabase.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from research.paper_cycle_engine import plan_cycle

DEFAULT_URL = "https://jarvis-gateio-attestor.beeniko33.workers.dev/v1/attestation"
EXPECTED_HOST = "jarvis-gateio-attestor.beeniko33.workers.dev"


def main() -> int:
    url = DEFAULT_URL
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != EXPECTED_HOST or parsed.path != "/v1/attestation":
        raise RuntimeError("attestor URL is not the pinned HTTPS endpoint")
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "JarvisLiveVerifierCheck/1.0"})
    with urlopen(request, timeout=20) as response:
        if response.status != 200 or urlparse(response.geturl()).hostname != EXPECTED_HOST:
            raise RuntimeError("attestor endpoint returned an unexpected response")
        raw = response.read(256_001)
    if len(raw) > 256_000:
        raise RuntimeError("attestor response exceeds size limit")
    observation = json.loads(raw)
    if not isinstance(observation, dict):
        raise RuntimeError("attestor returned a malformed payload")
    public_key = Path("config/gateio-verifier-public-key.b64").read_text().strip()
    now = datetime.now(timezone.utc)
    decision = plan_cycle(
        observation,
        {"health": "healthy", "mode": "paper",
         "kill_switch_engaged": False, "entries_paused": False},
        trusted_verifier_public_key=public_key,
        now=now,
        max_age_seconds=360,
        max_clock_skew_ms=5000,
    )
    if not decision["trust_attestation_verified"]:
        raise RuntimeError("live Gate.io attestation signature did not verify")
    if decision["status"] != "eligible_for_research_decision":
        raise RuntimeError("live observation failed planner checks: " + ",".join(decision["reasons"]))
    if observation.get("provenance_verified") is not False or observation.get("evidence_credit") is not False:
        raise RuntimeError("verifier improperly self-awarded provenance or evidence credit")
    print(json.dumps({
        "ok": True,
        "provider": observation["provider"],
        "instrument": observation["instrument"],
        "event_time": observation["event_time"],
        "received_at": observation["received_at"],
        "candidate": decision["candidate"],
        "signature_verified": True,
        "provenance_verified": False,
        "evidence_credit": False,
        "orders_submitted": 0,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

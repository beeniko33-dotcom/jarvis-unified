import base64
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from research.gateio_attestation_verifier import (
    VERIFIER_ID, canonical_observation, fetch_and_attest,
)
from research.paper_cycle_engine import plan_cycle


class Response:
    status = 200
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()
    def read(self):
        return self.payload
    def geturl(self):
        return "https://api.gateio.ws/api/v4/mock"


class VerifierTests(unittest.TestCase):
    def setUp(self):
        self.key = Ed25519PrivateKey.generate()
        self.private_b64 = base64.b64encode(
            self.key.private_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PrivateFormat.Raw,
                encryption_algorithm=serialization.NoEncryption(),
            )
        ).decode()
        self.public_b64 = base64.b64encode(
            self.key.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
        ).decode()
        self.now = datetime.fromtimestamp(1795092000, timezone.utc)

    def opener(self, request, timeout=10):
        url = request.full_url
        if "/spot/time" in url:
            return Response({"server_time": int(self.now.timestamp() * 1000)})
        if "/spot/candlesticks" in url:
            # Newest first as returned by Gate.io; create 60 completed candles.
            rows = []
            end_now = int(self.now.timestamp()) // 300 * 300
            for i in reversed(range(1, 61)):
                start = end_now - i * 300
                rows.append([str(start), "100", str(100 + i), str(110 + i),
                             str(90 + i), str(95 + i)])
            return Response(rows)
        if "/spot/order_book" in url:
            return Response({"id": 123, "bids": [["100.0", "1"]],
                             "asks": [["100.1", "1"]]})
        raise AssertionError(url)

    def test_fetches_and_signs_public_market_snapshot(self):
        result = fetch_and_attest(
            "BTC_USDT", private_key_b64=self.private_b64,
            opener=self.opener, now=lambda: self.now,
        )
        self.assertEqual(result["trust_attestation"]["verifier_id"], VERIFIER_ID)
        self.assertEqual(len(result["closes"]), 50)
        self.assertFalse(result["provenance_verified"])
        self.assertFalse(result["evidence_credit"])
        verified = self.key.public_key().verify(
            base64.b64decode(result["trust_attestation"]["signature"]),
            canonical_observation(result),
        )
        self.assertIsNone(verified)
        planned = plan_cycle(
            result,
            {"health": "healthy", "mode": "paper",
             "kill_switch_engaged": False, "entries_paused": False},
            trusted_verifier_public_key=self.public_b64,
            now=self.now,
        )
        self.assertTrue(planned["trust_attestation_verified"])
        self.assertFalse(planned["order_authorized"])
        self.assertEqual(planned["orders_submitted"], 0)

    def test_missing_signing_key_fails_closed(self):
        with self.assertRaises(RuntimeError):
            fetch_and_attest("BTC_USDT", private_key_b64=None, opener=self.opener,
                             now=lambda: self.now)

    def test_gap_in_history_is_rejected(self):
        def gapped(request, timeout=10):
            if "/spot/candlesticks" in request.full_url:
                return Response([[str(1795090000 - i * 600), "100", "100",
                                  "101", "99", "100"] for i in range(60)])
            return self.opener(request, timeout)
        with self.assertRaises(ValueError):
            fetch_and_attest("BTC_USDT", private_key_b64=self.private_b64,
                             opener=gapped, now=lambda: self.now)

    def test_unexpected_redirect_host_is_rejected(self):
        class Redirect(Response):
            def geturl(self):
                return "https://evil.example/steal"
        def redirect(request, timeout=10):
            return Redirect({"server_time": int(self.now.timestamp())})
        with self.assertRaises(RuntimeError):
            fetch_and_attest("BTC_USDT", private_key_b64=self.private_b64,
                             opener=redirect, now=lambda: self.now)


if __name__ == "__main__":
    unittest.main()

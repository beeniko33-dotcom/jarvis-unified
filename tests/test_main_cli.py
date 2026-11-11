import io
import json
import os
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from main import main


class MainCliTests(unittest.TestCase):
    def test_serve_accepts_custom_host_and_port(self):
        seen = {}

        def fake_serve(host, port, provider):
            seen["host"] = host
            seen["port"] = port
            seen["status"] = provider()

        with patch.dict(os.environ, {}, clear=True):
            with patch("apps.api.status.serve", fake_serve):
                main(["--serve", "--host", "localhost", "--port", "9001"])

        self.assertEqual(seen["host"], "localhost")
        self.assertEqual(seen["port"], 9001)
        self.assertEqual(seen["status"]["broker"], "paper")

    def test_status_prints_json_snapshot(self):
        buffer = io.StringIO()
        with patch.dict(os.environ, {}, clear=True):
            with redirect_stdout(buffer):
                main(["--status"])

        output = buffer.getvalue().splitlines()
        self.assertIn("Jarvis Unified", output[0])
        payload = json.loads(output[-1])
        self.assertEqual(payload["mode"], "paper")
        self.assertEqual(payload["broker"], "paper")
        self.assertTrue(payload["kill_switch"])
        self.assertIn("account", payload)

    def test_health_prints_ok_payload(self):
        buffer = io.StringIO()
        with patch.dict(os.environ, {}, clear=True):
            with redirect_stdout(buffer):
                main(["--health"])

        payload = json.loads(buffer.getvalue().strip().splitlines()[-1])
        self.assertEqual(payload, {"ok": True})

    def test_summary_prints_compact_snapshot(self):
        buffer = io.StringIO()
        with patch.dict(os.environ, {}, clear=True):
            with redirect_stdout(buffer):
                main(["--summary"])

        payload = json.loads(buffer.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["broker"], "paper")
        self.assertEqual(payload["open_positions"], 0)


if __name__ == "__main__":
    unittest.main()

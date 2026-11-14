import io
import json
import os
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from contextlib import redirect_stdout
from unittest.mock import patch

from main import main
from brokers.paper import PersistentPaperBroker
from core.models import OrderRequest, Side


class MainCliTests(unittest.TestCase):
    def test_paper_ledger_import_and_outcome_report_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = root / "paper.sqlite"
            learning = root / "learning.sqlite"
            broker = PersistentPaperBroker(Decimal("1000"), database_path=ledger)
            broker.place_order(
                OrderRequest("EURUSD", Side.BUY, Decimal("0.1"), Decimal("10"), "cli-entry")
            )
            broker.close_position("EURUSD", Decimal("8"))

            imported_output = io.StringIO()
            with redirect_stdout(imported_output):
                main([
                    "--import-paper-ledger",
                    "--paper-ledger-db", str(ledger),
                    "--learning-db", str(learning),
                ])
            imported = json.loads(imported_output.getvalue())
            self.assertTrue(imported["source_chain_verified"])
            self.assertGreater(imported["imported_events"], 0)

            report_output = io.StringIO()
            with redirect_stdout(report_output):
                main(["--paper-outcomes", "--learning-db", str(learning)])
            report = json.loads(report_output.getvalue())
            self.assertGreater(report["imported_ledger_events"], 0)
            self.assertEqual(report["order_count"], 2)

            shadow_output = io.StringIO()
            shadow_db = root / "shadow.sqlite"
            with redirect_stdout(shadow_output):
                main([
                    "--shadow-review", "--learning-db", str(learning),
                    "--shadow-db", str(shadow_db),
                ])
            shadow = json.loads(shadow_output.getvalue())
            self.assertIn("candidates", shadow)
            self.assertTrue(shadow_db.is_file())
            candidate_id = shadow["candidates"][0]["candidate_id"]

            history_output = io.StringIO()
            with redirect_stdout(history_output):
                main(["--shadow-history", "--shadow-db", str(shadow_db)])
            history = json.loads(history_output.getvalue())
            self.assertTrue(history["candidate_history"])

            decision_output = io.StringIO()
            with redirect_stdout(decision_output):
                main([
                    "--shadow-decision", candidate_id, "needs_more_evidence",
                    "--shadow-notes", "Need more verified observations.",
                    "--shadow-db", str(shadow_db),
                ])
            self.assertTrue(json.loads(decision_output.getvalue())["recorded"])

            history_after = io.StringIO()
            with redirect_stdout(history_after):
                main(["--shadow-history", "--shadow-db", str(shadow_db)])
            reviewed = next(
                item for item in json.loads(history_after.getvalue())["candidate_history"]
                if item["candidate_id"] == candidate_id
            )
            decisions = reviewed["owner_reviews"]
            self.assertEqual(decisions[0]["decision"], "needs_more_evidence")

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

    def test_version_prints_release_string(self):
        buffer = io.StringIO()
        with patch.dict(os.environ, {}, clear=True):
            with redirect_stdout(buffer):
                main(["--version"])

        self.assertIn("Jarvis Unified", buffer.getvalue().strip())
        self.assertIn("0.2.0", buffer.getvalue())

    def test_report_prints_combined_snapshot(self):
        buffer = io.StringIO()
        with patch.dict(os.environ, {}, clear=True):
            with redirect_stdout(buffer):
                main(["--report"])

        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["ok"], True)
        self.assertEqual(payload["version"], "0.2.0")
        self.assertEqual(payload["mode"], "paper")
        self.assertEqual(payload["broker"], "paper")

    def test_demo_prints_simulated_trade_snapshot(self):
        buffer = io.StringIO()
        with patch.dict(os.environ, {}, clear=True):
            with redirect_stdout(buffer):
                main(["--demo"])

        payload = json.loads(buffer.getvalue().splitlines()[-1])
        self.assertTrue(payload["demo"])
        self.assertEqual(payload["mode"], "paper")
        self.assertEqual(payload["broker"], "paper")
        self.assertEqual(payload["approved_order"]["symbol"], "AAPL")
        self.assertEqual(payload["closed_order"]["symbol"], "AAPL")
        self.assertFalse(payload["rejected_order"]["allowed"])
        self.assertEqual(payload["account"]["open_positions"], 0)
        self.assertEqual(payload["summary"]["open_positions"], 0)


if __name__ == "__main__":
    unittest.main()

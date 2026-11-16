from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from research.evidence_pipeline import ResearchEvidencePipeline
from research.public_sources import (
    PublicSourceRecord, SourceMetadata, fetch_frankfurter_daily,
    ingest_public_records, read_historical_ohlcv_csv,
)


class PublicSourceAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.now = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)
        self.pipeline = ResearchEvidencePipeline(Path(self.tmp.name) / "evidence.sqlite")

    def tearDown(self):
        self.tmp.cleanup()

    def test_csv_import_and_provenance_are_persisted_unverified(self):
        csv_path = Path(self.tmp.name) / "eurusd.csv"
        csv_path.write_text(
            "timestamp,open,high,low,close,volume\n"
            "2026-11-13T00:00:00Z,1.15,1.16,1.14,1.155,100\n",
            encoding="utf-8",
        )
        records = read_historical_ohlcv_csv(
            csv_path, symbol="EURUSD", timeframe="1d", now=self.now,
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].observation.values["close"], 1.155)
        result = ingest_public_records(
            records, pipeline=self.pipeline,
            provenance_database=Path(self.tmp.name) / "provenance.sqlite",
            now=self.now,
        )
        self.assertEqual(result["accepted"], 1)
        self.assertEqual(result["verified_observations"], 0)
        self.assertFalse(self.pipeline.report()["evidence_eligible"])

    def test_csv_rejects_naive_timestamps(self):
        csv_path = Path(self.tmp.name) / "bad.csv"
        csv_path.write_text(
            "timestamp,open,high,low,close\n"
            "2026-11-13T00:00:00,1.15,1.16,1.14,1.155\n",
            encoding="utf-8",
        )
        with self.assertRaises(ValueError):
            read_historical_ohlcv_csv(csv_path, symbol="EURUSD", timeframe="1d", now=self.now)

    def test_csv_rejects_invalid_ohlc_relationship(self):
        csv_path = Path(self.tmp.name) / "bad.csv"
        csv_path.write_text(
            "timestamp,open,high,low,close\n"
            "2026-11-13T00:00:00Z,1.15,1.10,1.14,1.155\n",
            encoding="utf-8",
        )
        with self.assertRaises(ValueError):
            read_historical_ohlcv_csv(csv_path, symbol="EURUSD", timeframe="1d", now=self.now)

    def test_csv_rejects_non_finite_and_negative_volume(self):
        csv_path = Path(self.tmp.name) / "bad.csv"
        csv_path.write_text(
            "timestamp,open,high,low,close,volume\n"
            "2026-11-13T00:00:00Z,1.15,1.16,1.14,1.155,-1\n",
            encoding="utf-8",
        )
        with self.assertRaises(ValueError):
            read_historical_ohlcv_csv(csv_path, symbol="EURUSD", timeframe="1d", now=self.now)

    def test_frankfurter_uses_fixed_allowlisted_https_host(self):
        with self.assertRaises(ValueError):
            fetch_frankfurter_daily(
                self.now.date(), base="EUR", quote="EUR", now=self.now,
            )

    def test_frankfurter_fetch_is_explicit_and_parses_expected_schema(self):
        class FakeResponse:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *args): return None
            def geturl(self):
                return "https://api.frankfurter.dev/v1/2026-11-15?from=EUR&to=USD"
            def read(self, size):
                return b'{"date":"2026-11-15","base":"EUR","rates":{"USD":1.16}}'
        class FakeOpener:
            def open(self, request, timeout):
                return FakeResponse()
        with patch("urllib.request.build_opener", return_value=FakeOpener()):
            record = fetch_frankfurter_daily(
                self.now.date(), now=self.now,
            )
        self.assertEqual(record.observation.values["rate"], 1.16)
        self.assertIn("api.frankfurter.dev", record.metadata.source_url)
        self.assertEqual(record.metadata.data_class, "daily_reference_rate_not_execution_quote")

    def test_redirect_to_unapproved_host_is_rejected(self):
        class FakeOpener:
            def open(self, request, timeout):
                raise HTTPError(
                    "https://api.frankfurter.dev/v1/2026-11-15?from=EUR&to=USD",
                    302, "redirect", {}, None,
                )
        with patch("urllib.request.build_opener", return_value=FakeOpener()):
            with self.assertRaises(RuntimeError):
                fetch_frankfurter_daily(self.now.date(), now=self.now)

    def test_metadata_sidecar_keeps_rights_unknown_and_candidate_status(self):
        csv_path = Path(self.tmp.name) / "eurusd.csv"
        csv_path.write_text(
            "timestamp,open,high,low,close\n"
            "2026-11-13T00:00:00Z,1.15,1.16,1.14,1.155\n",
            encoding="utf-8",
        )
        records = read_historical_ohlcv_csv(csv_path, symbol="EURUSD", timeframe="1d", now=self.now)
        ingest_public_records(
            records, pipeline=self.pipeline,
            provenance_database=Path(self.tmp.name) / "provenance.sqlite",
            now=self.now,
        )
        import sqlite3
        db = sqlite3.connect(Path(self.tmp.name) / "provenance.sqlite")
        row = db.execute(
            "SELECT licence_status, provenance FROM public_source_provenance"
        ).fetchone()
        db.close()
        self.assertEqual(row, ("unknown_user_must_confirm_rights", "candidate_unverified"))


if __name__ == "__main__":
    unittest.main()

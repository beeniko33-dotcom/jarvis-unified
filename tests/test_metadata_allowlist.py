"""PR #63: malformed metadata and sensitive-field exclusion.

The bridge reads lineage from a fixed allowlist of keys. That stops an
arbitrary *key* reaching a reflection, but says nothing about the *value*: a
nested object under an allowlisted key would be rendered verbatim, so a
credential carried inside it would land in the reflection text.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from research.execution_observations import ExecutionObservationJournal
from research.paper_reflection_bridge import build_paper_reflections
from research.reflection import ReflectionStore


class MetadataAllowlistTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.journal = ExecutionObservationJournal(root / "journal.sqlite3")
        self.store = ReflectionStore(root / "reflections.sqlite3")

    def _reflect(self, data: dict) -> str:
        self.journal.append(
            event_id="e1",
            event_type="paper_ledger_event",
            data={
                "source_event_type": "paper_close",
                "source_created_at": "2026-11-14T10:00:00+00:00",
                "symbol": "EURUSD",
                **data,
            },
        )
        reflections = build_paper_reflections(self.journal, self.store)
        self.assertEqual(len(reflections), 1)
        return reflections[0].facts[0]["statement"]

    def test_non_allowlisted_metadata_key_is_excluded(self) -> None:
        summary = self._reflect(
            {"metadata": {"api_key": "sk-live-SECRET", "password": "hunter2"}}
        )
        self.assertNotIn("sk-live-SECRET", summary)
        self.assertNotIn("hunter2", summary)

    def test_credential_inside_allowlisted_value_is_excluded(self) -> None:
        """A dict under an allowlisted key must not be rendered verbatim."""
        summary = self._reflect(
            {"metadata": {"quote_source": {"provider": "x", "api_key": "sk-live-SECRET"}}}
        )
        self.assertNotIn(
            "sk-live-SECRET", summary,
            "credential leaked through an allowlisted key's value",
        )

    def test_malformed_metadata_is_ignored(self) -> None:
        for bad in ("not-a-dict", 42, ["a", "b"], None):
            with self.subTest(metadata=bad):
                self.setUp()
                summary = self._reflect({"metadata": bad})
                self.assertIn("EURUSD", summary)

    def test_absent_lineage_stays_unknown_not_inferred(self) -> None:
        summary = self._reflect({})
        self.assertIn("realized_delta=unknown", summary)
        self.assertIn("commission_delta=unknown", summary)
        self.assertNotIn("strategy_id=", summary)

    def test_allowlisted_scalar_still_renders(self) -> None:
        summary = self._reflect(
            {"metadata": {"strategy_id": "sma-crossover-long", "experiment_id": "exp-7"}}
        )
        self.assertIn("strategy_id=sma-crossover-long", summary)
        self.assertIn("experiment_id=exp-7", summary)


if __name__ == "__main__":
    unittest.main()

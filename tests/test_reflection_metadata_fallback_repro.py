"""Regression tests for the metadata fallback in paper reflections.

The fallback lets a field arrive either as a typed top-level key or from the
event's ``metadata`` allowlist. The ledger backfill loop that guarantees
``realized_delta``/``commission_delta`` are always mentioned still tested
``key not in data``, which is only the top-level dict. A value supplied through
metadata was therefore rendered once with its real value and then again as
``unknown``, producing a self-contradictory fact in a reflection whose whole
purpose is to be factual.
"""
import unittest

from research.paper_reflection_bridge import _summary


class ReflectionMetadataFallbackTests(unittest.TestCase):
    def test_metadata_value_is_not_contradicted_by_unknown(self):
        data = {
            "source_event_type": "paper_close",
            "symbol": "EURUSD",
            "metadata": {"realized_delta": "-1.25"},
        }
        statement = _summary("paper_ledger_event", data)
        self.assertIn("realized_delta=-1.25", statement)
        self.assertNotIn("realized_delta=unknown", statement)

    def test_absent_ledger_field_is_still_reported_unknown(self):
        data = {"source_event_type": "paper_close", "symbol": "EURUSD"}
        statement = _summary("paper_ledger_event", data)
        self.assertIn("realized_delta=unknown", statement)
        self.assertIn("commission_delta=unknown", statement)

    def test_top_level_value_wins_over_metadata(self):
        data = {
            "source_event_type": "paper_close",
            "realized_delta": "2.50",
            "metadata": {"realized_delta": "-9.99"},
        }
        statement = _summary("paper_ledger_event", data)
        self.assertIn("realized_delta=2.50", statement)
        self.assertNotIn("-9.99", statement)

    def test_explicit_null_is_reported_unknown_once(self):
        data = {"source_event_type": "paper_close", "realized_delta": None}
        statement = _summary("paper_ledger_event", data)
        self.assertEqual(statement.count("realized_delta="), 1)
        self.assertIn("realized_delta=unknown", statement)

    def test_non_dict_metadata_is_ignored(self):
        data = {"source_event_type": "paper_close", "metadata": "not-a-dict"}
        statement = _summary("paper_ledger_event", data)
        self.assertIn("realized_delta=unknown", statement)

    def test_lineage_fields_still_render_from_metadata(self):
        data = {
            "source_event_type": "paper_close",
            "metadata": {
                "strategy_id": "sma-crossover-long",
                "strategy_version": "1.0.0",
                "experiment_id": "exp-7",
            },
        }
        statement = _summary("paper_ledger_event", data)
        self.assertIn("strategy_id=sma-crossover-long", statement)
        self.assertIn("strategy_version=1.0.0", statement)
        self.assertIn("experiment_id=exp-7", statement)


if __name__ == "__main__":
    unittest.main()

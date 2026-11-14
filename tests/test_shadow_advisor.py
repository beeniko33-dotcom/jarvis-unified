import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from research.paper_outcomes import PaperOutcomeReport
from research.shadow_advisor import (
    ShadowCandidateStore,
    generate_shadow_candidates,
)


class ShadowAdvisorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ShadowCandidateStore(Path(self.tmp.name) / "shadow.sqlite")
        self.now = datetime(2026, 11, 14, 12, tzinfo=timezone.utc)

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def report(**overrides):
        values = dict(
            journal_events=20,
            imported_ledger_events=12,
            source_ledger_ids=("ledger-a",),
            order_count=6,
            filled_orders=5,
            partial_orders=1,
            cancelled_orders=0,
            open_working_orders=0,
            unique_fill_ids=3,
            approved_decisions=6,
            rejected_decisions=2,
            reservation_rejections=1,
            broker_submission_errors=0,
            close_events=4,
            gross_realized_pnl="-2.5",
            commission_paid="0.5",
            net_realized_after_commission="-3.0",
            max_observed_drawdown_pct="1.2",
            drawdown_observations=10,
            missing_drawdown_observations=2,
            by_utc_day=(),
            limitations=("Event/day-level attribution only.",),
        )
        values.update(overrides)
        return PaperOutcomeReport(**values)

    def test_generates_evidence_linked_review_candidates(self):
        candidates = generate_shadow_candidates(self.report(), self.store, now=self.now)
        categories = {item.category for item in candidates}
        self.assertEqual(categories, {
            "negative_net_outcome", "partial_fill_review", "rejection_review",
            "mark_coverage", "drawdown_review",
        })
        self.assertTrue(all(item.status == "pending_owner_review" for item in candidates))
        self.assertTrue(all(item.confidence in {"low", "moderate"} for item in candidates))
        self.assertTrue(all(item.expires_at > item.review_due_at for item in candidates))
        self.assertEqual(len(self.store.list_candidates()), len(candidates))

    def test_candidate_generation_is_idempotent_for_same_evidence(self):
        first = generate_shadow_candidates(self.report(), self.store, now=self.now)
        second = generate_shadow_candidates(
            self.report(), self.store, now=self.now + timedelta(days=1)
        )
        self.assertEqual(
            {item.candidate_id for item in first},
            {item.candidate_id for item in second},
        )
        self.assertEqual(len(self.store.list_candidates()), len(first))

    def test_no_trade_history_only_recommends_more_authentic_evidence(self):
        report = self.report(
            journal_events=0, imported_ledger_events=0, source_ledger_ids=(),
            order_count=0, filled_orders=0, partial_orders=0, unique_fill_ids=0,
            approved_decisions=0, rejected_decisions=0, reservation_rejections=0,
            close_events=0, gross_realized_pnl="0", commission_paid="0",
            net_realized_after_commission="0", max_observed_drawdown_pct=None,
            drawdown_observations=0, missing_drawdown_observations=0,
        )
        candidates = generate_shadow_candidates(report, self.store, now=self.now)
        self.assertEqual([item.category for item in candidates], ["data_coverage"])

    def test_owner_review_is_append_only_and_cannot_promote_strategy(self):
        candidate = generate_shadow_candidates(self.report(), self.store, now=self.now)[0]
        self.store.record_owner_decision(
            candidate.candidate_id,
            "accepted_for_manual_review",
            notes="Review evidence only.",
            reviewed_at=self.now,
        )
        stored = next(
            item for item in self.store.list_candidates()
            if item["candidate_id"] == candidate.candidate_id
        )
        self.assertEqual(stored["owner_reviews"][0]["decision"], "accepted_for_manual_review")
        with self.assertRaises(ValueError):
            self.store.record_owner_decision(
                candidate.candidate_id, "approve_and_deploy", reviewed_at=self.now
            )

    def test_expired_candidates_are_hidden_by_default(self):
        generate_shadow_candidates(self.report(), self.store, now=self.now)
        later = self.now + timedelta(days=46)
        self.assertEqual(self.store.list_candidates(now=later), [])
        self.assertTrue(self.store.list_candidates(include_expired=True, now=later))

    def test_naive_generation_time_is_rejected(self):
        with self.assertRaises(ValueError):
            generate_shadow_candidates(
                self.report(), self.store, now=datetime(2026, 11, 14)
            )


if __name__ == "__main__":
    unittest.main()

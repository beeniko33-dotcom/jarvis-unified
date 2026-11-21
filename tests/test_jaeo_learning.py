from __future__ import annotations

import unittest

from research.jaeo_learning import build_learning_report, report_as_dict


class JaeoLearningTests(unittest.TestCase):
    def test_small_sample_is_not_overfit(self):
        report = build_learning_report([
            {"status": "completed", "errors": []},
            {"status": "failed", "errors": ["timeout"]},
        ])
        self.assertEqual(report.sample_size, 2)
        self.assertTrue(any("three" in item for item in report.recommendations))

    def test_recurring_errors_are_ranked(self):
        report = build_learning_report([
            {"status": "failed", "errors": ["timeout", "network"]},
            {"status": "failed", "errors": ["timeout"]},
            {"status": "completed", "errors": ["timeout"]},
        ])
        self.assertEqual(report.recurring_errors[0], ("timeout", 3))
        self.assertEqual(report.failed, 2)
        self.assertEqual(report.completed, 1)

    def test_blocked_tasks_do_not_recommend_bypassing_gates(self):
        report = build_learning_report([
            {"status": "blocked", "errors": ["approval missing"]},
            {"status": "blocked", "errors": ["approval missing"]},
            {"status": "completed", "errors": []},
        ])
        self.assertTrue(any("do not bypass" in item for item in report.recommendations))

    def test_invalid_records_and_statuses_are_ignored(self):
        report = build_learning_report([
            None,
            {"status": "running", "errors": ["not final"]},
            {"status": "completed", "errors": "malformed"},
        ])
        self.assertEqual(report.sample_size, 1)
        self.assertEqual(report.recurring_errors, ())

    def test_report_never_changes_policy_or_enables_self_modification(self):
        payload = report_as_dict(build_learning_report([
            {"status": "completed", "errors": []},
            {"status": "completed", "errors": []},
            {"status": "completed", "errors": []},
        ]))
        self.assertTrue(payload["requires_human_review"])
        self.assertFalse(payload["policy_changed"])
        self.assertFalse(payload["self_modification_enabled"])
        self.assertEqual(payload["mode"], "supervised")
        self.assertFalse(payload["live_trading_enabled"])


if __name__ == "__main__":
    unittest.main()

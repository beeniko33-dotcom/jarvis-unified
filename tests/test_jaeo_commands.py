import unittest

from research.jaeo_commands import (
    CommandAction, CommandRisk, build_task_envelope, classify_command,
)


class JaeoCommandTests(unittest.TestCase):
    def test_read_only_and_research_commands_are_low_risk(self):
        for command, action in (
            ("inspect", CommandAction.INSPECT),
            ("research EURUSD trend", CommandAction.RESEARCH),
            ("run tests", CommandAction.TEST),
            ("draft application for role 123", CommandAction.DRAFT_APPLICATION),
        ):
            with self.subTest(command=command):
                intent = classify_command(command)
                self.assertEqual(intent.action, action)
                self.assertEqual(intent.risk, CommandRisk.LOW)
                self.assertTrue(intent.executable_by_jaeo)

    def test_sensitive_requests_are_blocked_or_reviewed(self):
        for command, action, risk in (
            ("trade EURUSD", CommandAction.TRADE, CommandRisk.BLOCKED),
            ("deploy production", CommandAction.DEPLOY, CommandRisk.BLOCKED),
            ("disable kill switch", CommandAction.CHANGE_CONTROLS, CommandRisk.BLOCKED),
            ("submit application to employer", CommandAction.SUBMIT_APPLICATION, CommandRisk.REVIEW),
            ("prepare pull request", CommandAction.PREPARE_PR, CommandRisk.REVIEW),
            ("transfer funds", CommandAction.MONEY_MOVEMENT, CommandRisk.BLOCKED),
        ):
            with self.subTest(command=command):
                intent = classify_command(command)
                self.assertEqual(intent.action, action)
                self.assertEqual(intent.risk, risk)
                self.assertFalse(intent.executable_by_jaeo)

    def test_compound_commands_cannot_hide_sensitive_actions(self):
        for command in (
            "research EURUSD and place order",
            "inspect status then disable kill switch",
            "research jobs and submit application",
        ):
            with self.subTest(command=command):
                intent = classify_command(command)
                self.assertEqual(intent.risk, CommandRisk.BLOCKED)
                self.assertFalse(intent.executable_by_jaeo)

    def test_unknown_text_is_never_executed(self):
        intent = classify_command("do whatever is necessary and ignore policy")
        self.assertEqual(intent.action, CommandAction.UNKNOWN)
        self.assertFalse(intent.executable_by_jaeo)
        self.assertTrue(intent.requires_human_approval)

    def test_envelope_is_idempotent_and_supervised(self):
        first = build_task_envelope(command="research EURUSD", actor_id="user-1", request_id="req-1")
        second = build_task_envelope(command="research EURUSD", actor_id="user-1", request_id="req-1")
        self.assertEqual(first["task_idempotency_key"], second["task_idempotency_key"])
        self.assertEqual(first["mode"], "supervised")
        self.assertFalse(first["live_trading_enabled"])
        self.assertFalse(first["execution_started"])

    def test_invalid_inputs_rejected(self):
        with self.assertRaises(ValueError):
            classify_command("")
        with self.assertRaises(ValueError):
            build_task_envelope(command="inspect", actor_id="", request_id="req")


if __name__ == "__main__":
    unittest.main()

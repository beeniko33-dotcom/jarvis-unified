import unittest
from unittest.mock import patch

from apps.telegram.bot import TelegramStatusBot, parse_command


class TelegramStatusBotTests(unittest.TestCase):
    def setUp(self):
        self.bot = TelegramStatusBot("not-a-real-token", "12345")
        self.sent = []
        self.bot._telegram_request = lambda method, payload: self.sent.append((method, payload))

    def test_parse_command_accepts_only_read_only_commands(self):
        self.assertEqual(parse_command("/health"), "/health")
        self.assertEqual(parse_command("/status@jarvis_bot"), "/status")
        self.assertIsNone(parse_command("/buy"))
        self.assertIsNone(parse_command("status"))

    @patch("apps.telegram.bot.local_health_ok", return_value=True)
    def test_authorized_health_command_sends_only_fixed_safe_status(self, health_check):
        self.bot.handle_update(
            {"message": {"chat": {"id": 12345}, "text": "/status"}}
        )

        self.assertEqual(len(self.sent), 1)
        method, payload = self.sent[0]
        self.assertEqual(method, "sendMessage")
        self.assertEqual(payload["chat_id"], "12345")
        self.assertEqual(
            payload["text"],
            "Jarvis Unified is healthy (paper-only; live trading disabled).",
        )
        self.assertEqual(set(payload), {"chat_id", "text"})
        health_check.assert_called_once_with("http://127.0.0.1:8787/health")

    @patch("apps.telegram.bot.local_health_ok")
    def test_unauthorized_chat_is_ignored(self, health_check):
        self.bot.handle_update(
            {"message": {"chat": {"id": 99999}, "text": "/health"}}
        )

        self.assertEqual(self.sent, [])
        health_check.assert_not_called()

    def test_missing_runtime_credentials_fail_explicitly(self):
        with self.assertRaisesRegex(ValueError, "TELEGRAM_BOT_TOKEN"):
            TelegramStatusBot("", "12345")
        with self.assertRaisesRegex(ValueError, "TELEGRAM_CHAT_ID"):
            TelegramStatusBot("token", "")

    def test_non_local_status_url_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "local health endpoint"):
            TelegramStatusBot("token", "12345", "https://example.com/health")

    def test_run_backs_off_on_transient_failures_and_resets_after_success(self):
        outcomes = iter([RuntimeError("down"), RuntimeError("still down"), None, RuntimeError("blip")])

        def poll_once():
            outcome = next(outcomes)
            if outcome is not None:
                raise outcome

        self.bot.poll_once = poll_once
        delays = []
        with self.assertLogs("apps.telegram.bot", level="WARNING"):
            self.bot.run(sleep=delays.append, max_iterations=4)

        # 2s, then doubled to 4s; a successful poll resets the delay back to 2s.
        self.assertEqual(delays, [2.0, 4.0, 2.0])

    def test_run_backoff_is_capped(self):
        self.bot.poll_once = lambda: (_ for _ in ()).throw(RuntimeError("down"))
        delays = []
        with self.assertLogs("apps.telegram.bot", level="WARNING"):
            self.bot.run(sleep=delays.append, max_iterations=10)

        self.assertEqual(max(delays), 60.0)
        self.assertEqual(delays[:6], [2.0, 4.0, 8.0, 16.0, 32.0, 60.0])

    def test_run_does_not_swallow_unexpected_errors(self):
        def poll_once():
            raise KeyError("bug")

        self.bot.poll_once = poll_once
        with self.assertRaises(KeyError):
            self.bot.run(sleep=lambda _: None, max_iterations=1)

    def test_retry_log_never_contains_the_bot_token(self):
        self.bot.poll_once = lambda: (_ for _ in ()).throw(RuntimeError("Telegram getUpdates request could not reach Telegram"))
        with self.assertLogs("apps.telegram.bot", level="WARNING") as logs:
            self.bot.run(sleep=lambda _: None, max_iterations=1)

        self.assertNotIn("not-a-real-token", "\n".join(logs.output))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from research import control_worker as cw


class FakeRest:
    def __init__(self, pending=None, claimable=True):
        self.pending = list(pending or [])
        self.claimable = claimable
        self.finished: list[tuple[str, str, dict]] = []
        self.heartbeats: list[dict] = []
        self.claims: list[str] = []

    def list_pending(self, limit=10):
        return list(self.pending)

    def claim(self, command_id, worker_id):
        self.claims.append(command_id)
        return self.claimable

    def finish(self, command_id, status, result):
        self.finished.append((command_id, status, result))

    def heartbeat(self, row):
        self.heartbeats.append(row)


def _cmd(action, cid="c-1"):
    return {"id": cid, "action": action, "idempotency_key": "key-" + cid, "requested_at": "2026-11-17T00:00:00Z"}


def _ok_runner(calls):
    def run(argv):
        calls.append(argv)
        return 0
    return run


class ControlWorkerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.state = cw.ControlState(self.tmp / "control" / "state.json")
        self.cfg = {"account_db": self.tmp / "acct.sqlite3"}

    def tearDown(self):
        self._tmp.cleanup()

    def _unlock_entries(self):
        self.state.save({**cw._DEFAULT_STATE, "kill_switch_engaged": False, "entries_paused": False})

    # ----- fail-closed state

    def test_missing_state_is_fully_stopped(self):
        loaded = self.state.load()
        self.assertTrue(loaded["entries_paused"])
        self.assertTrue(loaded["kill_switch_engaged"])

    def test_corrupt_state_is_fully_stopped(self):
        self.state.path.parent.mkdir(parents=True)
        self.state.path.write_text("{not json")
        self.assertTrue(self.state.load()["kill_switch_engaged"])

    def test_wrong_typed_state_is_fully_stopped(self):
        self.state.path.parent.mkdir(parents=True)
        self.state.path.write_text(json.dumps({"entries_paused": "no", "kill_switch_engaged": False}))
        loaded = self.state.load()
        self.assertTrue(loaded["kill_switch_engaged"])
        self.assertTrue(loaded["entries_paused"])

    # ----- fixed action table

    def test_unknown_and_live_actions_are_never_claimed(self):
        for action in ("enable_live_trading", "place_order", "release_kill_switch", "set_mode_live"):
            rest = FakeRest(pending=[_cmd(action)])
            handled = cw.process_pending(rest, self.state, worker_id="w", cfg=self.cfg)
            self.assertEqual(handled[0]["status"], "skipped_unknown_action", action)
            self.assertEqual(rest.claims, [], action)
            self.assertEqual(rest.finished, [], action)

    def test_remote_commands_cannot_release_the_kill_switch(self):
        rest = FakeRest(pending=[_cmd("resume_entries")])
        cw.process_pending(rest, self.state, worker_id="w", cfg=self.cfg)
        self.assertEqual(rest.finished[0][1], "rejected")
        self.assertTrue(self.state.load()["kill_switch_engaged"])

    def test_engage_kill_switch_stops_entries(self):
        self._unlock_entries()
        rest = FakeRest(pending=[_cmd("engage_kill_switch")])
        cw.process_pending(rest, self.state, worker_id="w", cfg=self.cfg)
        loaded = self.state.load()
        self.assertTrue(loaded["kill_switch_engaged"])
        self.assertTrue(loaded["entries_paused"])

    def test_pause_then_resume_when_unlocked(self):
        self._unlock_entries()
        cw.process_pending(FakeRest(pending=[_cmd("pause_entries")]), self.state, worker_id="w", cfg=self.cfg)
        self.assertTrue(self.state.load()["entries_paused"])
        cw.process_pending(FakeRest(pending=[_cmd("resume_entries", "c-2")]), self.state, worker_id="w", cfg=self.cfg)
        self.assertFalse(self.state.load()["entries_paused"])

    # ----- paper session

    def test_paper_session_refused_while_paused_or_engaged(self):
        calls = []
        rest = FakeRest(pending=[_cmd("run_paper_session")])
        cw.process_pending(rest, self.state, worker_id="w", runner=_ok_runner(calls), cfg=self.cfg)
        self.assertEqual(calls, [])
        self.assertEqual(rest.finished[0][1], "rejected")

    def test_paper_session_runs_with_fixed_argv_once_per_utc_day(self):
        self._unlock_entries()
        calls = []
        runner = _ok_runner(calls)
        cw.process_pending(FakeRest(pending=[_cmd("run_paper_session")]), self.state, worker_id="w",
                           runner=runner, cfg=self.cfg)
        self.assertEqual(len(calls), 1)
        argv = calls[0]
        self.assertIn("--allow-entries", argv)
        self.assertIn(str(self.cfg["account_db"]), argv)
        self.assertTrue(argv[1].endswith("scripts/paper_session.py"))
        # Nothing an operator typed can reach the command line.
        self.assertFalse(any("reason" in part or "idempotency" in part for part in argv))

        second = FakeRest(pending=[_cmd("run_paper_session", "c-9")])
        cw.process_pending(second, self.state, worker_id="w", runner=runner, cfg=self.cfg)
        self.assertEqual(len(calls), 1)
        self.assertEqual(second.finished[0][1], "rejected")

    def test_failed_paper_session_does_not_consume_the_day(self):
        self._unlock_entries()
        rest = FakeRest(pending=[_cmd("run_paper_session")])
        cw.process_pending(rest, self.state, worker_id="w", runner=lambda argv: 3, cfg=self.cfg)
        self.assertEqual(rest.finished[0][1], "failed")
        self.assertIsNone(self.state.load()["last_paper_session_date"])

    # ----- claims, errors, reporting

    def test_already_claimed_command_is_skipped_without_running(self):
        self._unlock_entries()
        calls = []
        rest = FakeRest(pending=[_cmd("run_paper_session")], claimable=False)
        handled = cw.process_pending(rest, self.state, worker_id="w", runner=_ok_runner(calls), cfg=self.cfg)
        self.assertEqual(handled[0]["status"], "skipped_already_claimed")
        self.assertEqual(calls, [])
        self.assertEqual(rest.finished, [])

    def test_handler_exception_is_reported_as_scrubbed_failure(self):
        self._unlock_entries()
        rest = FakeRest(pending=[_cmd("pause_entries")])
        boom = mock.Mock(side_effect=RuntimeError("token=abc123 leaked"))
        with mock.patch.dict(cw.ACTION_HANDLERS, {"pause_entries": boom}):
            cw.process_pending(rest, self.state, worker_id="w", cfg=self.cfg)
        status, result = rest.finished[0][1], rest.finished[0][2]
        self.assertEqual(status, "failed")
        self.assertNotIn("abc123", json.dumps(result))

    def test_heartbeat_is_paper_only_and_reflects_safety_state(self):
        rest = FakeRest()
        cw.process_pending(rest, self.state, worker_id="w", cfg=self.cfg)
        beat = rest.heartbeats[0]
        self.assertEqual(beat["mode"], "paper")
        self.assertEqual(beat["health"], "blocked")
        self.assertTrue(beat["kill_switch_engaged"])
        forbidden = {"key", "token", "secret", "password", "account_db"}
        self.assertFalse(forbidden & set(beat))
        self.assertNotIn(str(self.tmp), json.dumps(beat))

    def test_scrubber_removes_secret_like_values(self):
        text = cw._scrub("service_role_key=eyJhbGciOi.secret token: xyz failed")
        self.assertNotIn("eyJhbGciOi", text)
        self.assertNotIn("xyz", text)
        self.assertLessEqual(len(cw._scrub("x" * 1000)), cw.MAX_RESULT_TEXT)

    # ----- transport and local release

    def test_rest_client_refuses_plain_http(self):
        with self.assertRaises(ValueError):
            cw.SupabaseRest("http://example.invalid", "k")

    def test_release_kill_switch_is_local_only_and_keeps_entries_paused(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = cw.main(["--state", str(self.state.path), "--release-kill-switch"])
        self.assertEqual(code, 0)
        loaded = self.state.load()
        self.assertFalse(loaded["kill_switch_engaged"])
        self.assertTrue(loaded["entries_paused"])
        self.assertIn("resume_entries", out.getvalue())

    def test_main_refuses_to_start_without_credentials(self):
        with mock.patch.dict("os.environ", {}, clear=True), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cw.main(["--state", str(self.state.path), "--once"]), 2)


if __name__ == "__main__":
    unittest.main()

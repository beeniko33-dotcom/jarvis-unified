import tempfile
import unittest
from pathlib import Path

from research.reflection import ReflectionStore, SessionEvent


class ReflectionStoreTests(unittest.TestCase):
    def test_reflection_cites_facts_and_separates_owner_corrections(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ReflectionStore(Path(tmp) / "learning.sqlite3")
            events = [
                SessionEvent("e2", "2026-11-14T10:02:00Z", "paper_test",
                             "Paper replay completed with 0 accepted orders", "ci://run/200"),
                SessionEvent("e1", "2026-11-14T10:01:00Z", "owner_feedback",
                             "Owner requested concise daily summaries", "chat://feedback/1",
                             owner_correction=True),
            ]
            result = store.build(session_id="session-1", events=events)
            self.assertEqual(result.event_ids, ["e1", "e2"])
            self.assertEqual(len(result.owner_corrections), 1)
            self.assertEqual(result.facts[0]["source_ref"], "chat://feedback/1")
            self.assertEqual(store.get(result.reflection_id), result)

    def test_replaying_same_session_events_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ReflectionStore(Path(tmp) / "learning.sqlite3")
            events = [
                SessionEvent("entry-1", "2026-11-14T10:00:00Z", "paper_entry",
                             "Paper entry accepted", "ledger://event/1"),
                SessionEvent("exit-1", "2026-11-14T10:05:00Z", "paper_exit",
                             "Paper exit closed at a loss", "ledger://event/2"),
            ]
            first = store.build(session_id="session-replay", events=events)
            second = store.build(session_id="session-replay", events=reversed(events))
            self.assertEqual(first.reflection_id, second.reflection_id)
            self.assertEqual(first.created_at, second.created_at)
            self.assertEqual(store.list_for_session("session-replay"), [first])

    def test_changed_source_fact_creates_distinct_reflection_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ReflectionStore(Path(tmp) / "learning.sqlite3")
            first = store.build(session_id="session-revision", events=[
                SessionEvent("e1", "2026-11-14T10:00:00Z", "paper", "Original fact", "ledger://1")
            ])
            second = store.build(session_id="session-revision", events=[
                SessionEvent("e1", "2026-11-14T10:00:00Z", "paper", "Corrected fact", "ledger://1")
            ])
            self.assertNotEqual(first.reflection_id, second.reflection_id)
            self.assertEqual(len(store.list_for_session("session-revision")), 2)

    def test_repeated_event_type_is_only_a_hypothesis(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ReflectionStore(Path(tmp) / "learning.sqlite3")
            events = [
                SessionEvent("a", "2026-11-14T10:00:00Z", "retry",
                             "Retry attempt one", "log://1"),
                SessionEvent("b", "2026-11-14T10:01:00Z", "retry",
                             "Retry attempt two", "log://2"),
            ]
            result = store.build(session_id="s", events=events)
            self.assertTrue(result.hypotheses)
            self.assertIn("not proof", result.hypotheses[0])

    def test_unknowns_are_explicit_and_empty_events_do_not_invent_facts(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ReflectionStore(Path(tmp) / "learning.sqlite3")
            result = store.build(session_id="empty", events=[])
            self.assertEqual(result.facts, [])
            self.assertEqual(result.event_count, 0)
            self.assertTrue(result.unknowns)

    def test_rejects_duplicate_event_ids_naive_timestamps_and_bad_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ReflectionStore(Path(tmp) / "learning.sqlite3")
            duplicate = SessionEvent("x", "2026-11-14T10:00:00Z", "test", "a", "ref")
            with self.assertRaises(ValueError):
                store.build(session_id="s", events=[duplicate, duplicate])
            with self.assertRaises(ValueError):
                store.build(session_id="s", events=[
                    SessionEvent("y", "2026-11-14T10:00:00", "test", "a", "ref")
                ])
            with self.assertRaises(ValueError):
                store.build(session_id="s", events=[
                    SessionEvent("z", "2026-11-14T10:00:00Z", "test", "a", "ref", "magic")
                ])


if __name__ == "__main__":
    unittest.main()

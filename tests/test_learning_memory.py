"""Tests for the isolated, persistent personal learning memory store."""
import json
import tempfile
import unittest
from pathlib import Path

from core.learning.memory_store import MemoryStore


class MemoryStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "learning.sqlite3"

    def test_explicit_memory_survives_restart(self):
        store = MemoryStore(self.db)
        saved = store.put("communication", "detail", "Concise by default")
        reopened = MemoryStore(self.db)
        loaded = reopened.get("communication", "detail")
        self.assertEqual(loaded.content, "Concise by default")
        self.assertEqual(loaded.source, "explicit_user_feedback")
        self.assertEqual(loaded.confidence, 1.0)
        self.assertEqual(saved.memory_id, loaded.memory_id)

    def test_explicit_feedback_overrides_inference(self):
        store = MemoryStore(self.db)
        store.put("workflow", "report", "Maybe weekly", source="inferred_candidate")
        explicit = store.put("workflow", "report", "Daily report")
        self.assertEqual(explicit.content, "Daily report")
        self.assertEqual(explicit.source, "explicit_user_feedback")

    def test_inference_cannot_overwrite_explicit_feedback(self):
        store = MemoryStore(self.db)
        explicit = store.put("workflow", "report", "Daily report")
        returned = store.put(
            "workflow", "report", "Maybe monthly", source="inferred_candidate"
        )
        self.assertEqual(returned.memory_id, explicit.memory_id)
        self.assertEqual(returned.content, "Daily report")

    def test_repeated_choice_has_lower_default_confidence(self):
        store = MemoryStore(self.db)
        item = store.put("markets", "focus", "EURUSD", source="repeated_choice")
        self.assertEqual(item.confidence, 0.7)

    def test_update_records_history_without_storing_content_in_event(self):
        store = MemoryStore(self.db)
        item = store.put("style", "tone", "Calm")
        store.put("style", "tone", "Calm and direct")
        events = store.event_history(memory_id=item.memory_id)
        self.assertEqual([event["action"] for event in events], ["created", "updated"])
        self.assertNotIn("Calm", json.dumps(events))

    def test_delete_removes_content_but_keeps_deletion_event(self):
        store = MemoryStore(self.db)
        item = store.put("style", "tone", "Calm")
        self.assertTrue(store.delete("style", "tone"))
        self.assertIsNone(store.get("style", "tone"))
        self.assertEqual(store.event_history(memory_id=item.memory_id)[-1]["action"], "deleted")
        self.assertFalse(store.delete("style", "tone"))

    def test_export_is_valid_json_and_excludes_deleted_memories(self):
        store = MemoryStore(self.db)
        store.put("style", "tone", "Calm")
        store.put("style", "detail", "Detailed")
        store.delete("style", "tone")
        exported = json.loads(store.export_json())
        self.assertEqual([item["memory_key"] for item in exported], ["detail"])

    def test_expired_memories_are_hidden_by_default(self):
        store = MemoryStore(self.db)
        store.put(
            "workflow", "old", "Old preference",
            expires_at="2000-01-01T00:00:00+00:00",
        )
        self.assertEqual(store.list_memories(), [])
        self.assertEqual(len(store.list_memories(include_expired=True)), 1)

    def test_explicit_confidence_must_be_one(self):
        store = MemoryStore(self.db)
        with self.assertRaises(ValueError):
            store.put("style", "tone", "Calm", confidence=0.8)

    def test_invalid_source_and_timezone_are_rejected(self):
        store = MemoryStore(self.db)
        with self.assertRaises(ValueError):
            store.put("style", "tone", "Calm", source="model_guess")
        with self.assertRaises(ValueError):
            store.put("style", "tone", "Calm", review_after="2030-01-01T00:00:00")


if __name__ == "__main__":
    unittest.main()

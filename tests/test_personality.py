import tempfile
import unittest
from pathlib import Path

from core.learning.memory_store import MemoryStore
from core.learning.personality import CORE_PERSONALITY, build_personality_context


class PersonalityContextTests(unittest.TestCase):
    def test_uses_stable_personality_and_saved_preferences(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = MemoryStore(Path(tmp) / "memory.sqlite3")
            store.put("communication", "report_style", "Concise daily reports")
            result = build_personality_context(store)
            self.assertIn("You are Jarvis", result)
            self.assertIn("Concise daily reports", result)
            self.assertIn("explicit_user_feedback", result)
            self.assertIn("not system policy", result)

    def test_inferred_preference_is_labelled_as_inferred(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = MemoryStore(Path(tmp) / "memory.sqlite3")
            store.put("workflow", "research", "Prefer a research-first workflow",
                      source="inferred_candidate")
            result = build_personality_context(store)
            self.assertIn("inferred_candidate", result)
            self.assertIn("confidence=0.40", result)

    def test_empty_profile_is_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = build_personality_context(MemoryStore(Path(tmp) / "memory.sqlite3"))
            self.assertIn("No durable owner preferences", result)
            self.assertIn("Never change risk limits", CORE_PERSONALITY)


if __name__ == "__main__":
    unittest.main()

import unittest

from research.notification_preferences import validate_preferences


class NotificationPreferenceTests(unittest.TestCase):
    def test_default_is_opted_out(self):
        result = validate_preferences({})
        self.assertFalse(result.enabled)
        self.assertEqual(result.categories, frozenset())

    def test_accepts_explicit_opt_in_and_quiet_hours(self):
        result = validate_preferences({
            "enabled": True,
            "categories": ["job_matches", "jaeo_tasks"],
            "quiet_start": "22:00",
            "quiet_end": "07:00",
            "timezone": "Africa/Lagos",
        })
        self.assertTrue(result.enabled)
        self.assertIn("job_matches", result.categories)

    def test_rejects_delivery_without_opt_in_and_bad_hours(self):
        with self.assertRaises(ValueError):
            validate_preferences({"enabled": False, "categories": ["job_matches"]})
        with self.assertRaises(ValueError):
            validate_preferences({"enabled": True, "categories": ["job_matches"], "quiet_start": "25:00", "quiet_end": "07:00"})
        with self.assertRaises(ValueError):
            validate_preferences({"enabled": True, "categories": ["unknown"]})


if __name__ == "__main__":
    unittest.main()

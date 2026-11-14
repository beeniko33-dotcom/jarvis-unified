import unittest

from core.feature_registry import feature_state_inventory


class FeatureRegistryTests(unittest.TestCase):
    def test_inventory_is_read_only_and_paper_only(self):
        inventory = feature_state_inventory()
        self.assertTrue(inventory["read_only"])
        self.assertEqual(inventory["execution_mode"], "paper_only")
        self.assertEqual(inventory["schema_version"], 1)

    def test_every_feature_has_explanation_and_boundary(self):
        inventory = feature_state_inventory()
        self.assertGreaterEqual(len(inventory["features"]), 8)
        ids = set()
        for feature in inventory["features"]:
            self.assertTrue(feature["id"])
            self.assertNotIn(feature["id"], ids)
            ids.add(feature["id"])
            self.assertIn(feature["state"], {"enabled", "disabled", "experimental", "unavailable"})
            self.assertTrue(feature["reason"])
            self.assertTrue(feature["risk_boundary"])
            self.assertIsInstance(feature["dependencies"], list)

    def test_safety_controls_are_not_mutable_from_inventory(self):
        inventory = feature_state_inventory()
        kill_switch = next(item for item in inventory["features"] if item["id"] == "kill_switch")
        self.assertEqual(kill_switch["state"], "enabled")
        self.assertIn("cannot change", kill_switch["risk_boundary"])
        self.assertFalse(any("set_" in key or "toggle" in key for key in inventory))

    def test_returned_inventory_is_detached(self):
        first = feature_state_inventory()
        first["features"][0]["state"] = "disabled"
        second = feature_state_inventory()
        self.assertEqual(second["features"][0]["state"], "enabled")


if __name__ == "__main__":
    unittest.main()

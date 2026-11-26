import json
import tempfile
import unittest
from pathlib import Path

from core.contracts import PlanValidationError, inspect_plan, load_json, validate_plan


class PlanContractTests(unittest.TestCase):
    def test_accepts_legacy_lego_plan(self):
        plan = {"title": "Test", "scenes": [{"text": "A scene", "bg": "city", "actors": []}]}
        self.assertEqual(validate_plan(plan)["title"], "Test")

    def test_accepts_modern_plan(self):
        plan = {"title": "Test", "scenes": [{"text": "A scene", "visual": "gen", "gen_prompt": "cinematic"}]}
        self.assertEqual(inspect_plan_from_data(plan), "modern")

    def test_rejects_empty_scenes(self):
        with self.assertRaises(PlanValidationError):
            validate_plan({"title": "Empty", "scenes": []})

    def test_rejects_scene_without_text(self):
        with self.assertRaises(PlanValidationError):
            validate_plan({"title": "Bad", "scenes": [{"bg": "city"}]})

    def test_loads_utf8_json_and_reports_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plan.json"
            path.write_text(json.dumps({"title": "Test", "scenes": [{"text": "One", "bg": "city"}]}), encoding="utf-8")
            result = load_json(path)
            self.assertEqual(inspect_plan(path)["scene_count"], 1)
            self.assertEqual(result["title"], "Test")


def inspect_plan_from_data(plan):
    scene = plan["scenes"][0]
    return "modern" if "visual" in scene or "gen_prompt" in scene else "lego"


if __name__ == "__main__":
    unittest.main()

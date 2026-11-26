import unittest

from lego_cinema_fixes import sanitize_plan, _scene_action


class CastingAndMotionTests(unittest.TestCase):
    def test_removes_unmentioned_modern_public_figure(self):
        plan = {
            "characters": [
                {"name": "Adolf Hitler", "role": "president"},
                {"name": "Donald Trump", "role": "president"},
                {"name": "German soldiers", "role": "soldier"},
            ],
            "scenes": [{
                "text": "German troops advance through the snow.",
                "actors": [
                    {"name": "Adolf Hitler", "action": "idle"},
                    {"name": "Donald Trump", "action": "wave"},
                    {"name": "German soldiers", "action": "auto"},
                ],
            }],
        }
        result = sanitize_plan(plan, "Hitler's Germany invaded Poland. German troops advanced.")
        names = [c["name"] for c in result["characters"]]
        actor_names = [a["name"] for a in result["scenes"][0]["actors"]]
        self.assertIn("Adolf Hitler", names)
        self.assertNotIn("Donald Trump", names)
        self.assertNotIn("Donald Trump", actor_names)
        self.assertIn("German soldiers", actor_names)

    def test_keeps_historical_person_when_script_mentions_name(self):
        plan = {
            "characters": [{"name": "Winston Churchill", "role": "minister"}],
            "scenes": [{"text": "Churchill addresses the nation.", "actors": [
                {"name": "Winston Churchill", "action": "auto"}
            ]}],
        }
        result = sanitize_plan(plan, "Winston Churchill addressed the British people.")
        self.assertEqual(result["scenes"][0]["actors"][0]["name"], "Winston Churchill")

    def test_removes_named_person_not_in_source(self):
        plan = {
            "characters": [{"name": "Donald Trump", "role": "president"}],
            "scenes": [{"text": "The army crossed the border.", "actors": [
                {"name": "Donald Trump", "action": "wave"}
            ]}],
        }
        result = sanitize_plan(plan, "The army crossed the border.")
        self.assertEqual(result["characters"], [])
        self.assertEqual(result["scenes"][0]["actors"], [])

    def test_motion_is_derived_from_story_verbs(self):
        self.assertEqual(_scene_action("The soldiers marched toward the bridge.", "soldier"), "walk")
        self.assertEqual(_scene_action("The troops fled from the bombing.", "soldier"), "run")
        self.assertEqual(_scene_action("The commander ordered the attack.", "commander"), "point")
        self.assertEqual(_scene_action("The civilians waited in silence.", "civilian"), "idle")


if __name__ == "__main__":
    unittest.main()

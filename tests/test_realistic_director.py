import unittest

from realistic_director import prepare_plan


class RealisticDirectorTests(unittest.TestCase):
    def test_removes_unrelated_named_people_from_legacy_plan(self):
        script = "In 1941 Germany invaded the Soviet Union. German troops advanced toward Leningrad."
        plan = {
            "title": "World War II",
            "characters": [
                {"name": "Adolf Hitler", "role": "dictator"},
                {"name": "Donald Trump", "role": "president"},
                {"name": "German soldiers", "role": "soldiers"},
            ],
            "scenes": [{
                "text": "German troops advanced toward Leningrad.",
                "actors": [
                    {"name": "Donald Trump", "action": "wave"},
                    {"name": "German Soldier", "action": "run"},
                ],
                "props": [{"name": "tank"}],
            }],
        }
        result = prepare_plan(plan, script, "history")
        character_names = [x["name"] for x in result["characters"]]
        actor_names = [x["name"] for x in result["scenes"][0]["actors"]]
        self.assertNotIn("Donald Trump", character_names)
        self.assertNotIn("Donald Trump", actor_names)
        self.assertIn("German Soldier", actor_names)

    def test_scene_queries_are_about_scene_not_film_title(self):
        script = "On December 7, 1941, Japanese aircraft attacked Pearl Harbor."
        plan = {
            "title": "The Entire History of World War II",
            "scenes": [{"text": "Japanese aircraft attacked Pearl Harbor."}],
        }
        result = prepare_plan(plan, script, "history")
        queries = result["scenes"][0]["queries"]
        self.assertTrue(any("Pearl Harbor" in q for q in queries))
        self.assertFalse(any("Entire History" in q for q in queries))

    def test_historical_prompt_forbids_modern_anachronisms(self):
        script = "German soldiers advanced toward Moscow in winter 1941."
        plan = {"title": "Eastern Front", "scenes": [{"text": script}]}
        result = prepare_plan(plan, script, "history")
        prompt = result["scenes"][0]["gen_prompt"].lower()
        self.assertIn("historically faithful", prompt)
        self.assertIn("no contemporary politicians", prompt)
        self.assertIn("photorealistic", prompt)

    def test_adds_shot_and_camera_direction(self):
        script = "Thousands of soldiers crossed the bridge."
        plan = {"title": "Battle", "scenes": [{"text": script}]}
        scene = prepare_plan(plan, script, "history")["scenes"][0]
        self.assertEqual(scene["shot_type"], "extreme_wide")
        self.assertEqual(scene["camera_direction"], "slow_track")

    def test_name_banner_requires_person_in_that_scene(self):
        script = "Winston Churchill addressed the nation. German troops advanced."
        plan = {
            "title": "War",
            "scenes": [{
                "text": "German troops advanced.",
                "banner": {"kind": "name", "text": "Winston Churchill", "sub": "Prime Minister"},
            }],
        }
        result = prepare_plan(plan, script, "history")
        self.assertEqual(result["scenes"][0]["banner"]["kind"], "none")


if __name__ == "__main__":
    unittest.main()

import unittest

from cinematic_director import direct_plan, direct_scene


class CinematicDirectorTests(unittest.TestCase):
    def test_run_scene_gets_tracking_shot(self):
        scene = direct_scene({"text": "He runs toward the forest."})
        self.assertEqual(scene["action"], "run")
        self.assertEqual(scene["camera_move"], "tracking")
        self.assertEqual(scene["environment"], "forest")

    def test_reaction_scene_gets_close_up(self):
        scene = direct_scene({"text": "He notices smoke rising nearby."})
        self.assertEqual(scene["action"], "react")
        self.assertEqual(scene["shot_type"], "close_up")
        self.assertEqual(scene["mood"], "curiosity")

    def test_explicit_user_direction_is_preserved(self):
        scene = direct_scene({
            "text": "He walks home.",
            "action": "observe",
            "shot_type": "wide",
        })
        self.assertEqual(scene["action"], "observe")
        self.assertEqual(scene["shot_type"], "wide")

    def test_plan_keeps_scene_order_and_count(self):
        scenes = [{"text": "He walks."}, {"text": "He runs."}]
        directed = direct_plan(scenes)
        self.assertEqual(len(directed), 2)
        self.assertEqual([x["action"] for x in directed], ["walk", "run"])
        self.assertEqual([x["shot_index"] for x in directed], [0, 1])


if __name__ == "__main__":
    unittest.main()

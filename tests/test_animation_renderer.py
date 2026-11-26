import unittest

from animation_renderer import BLENDER_SOURCE, split_script


class AnimationRendererTests(unittest.TestCase):
    def test_script_is_split_into_scene_beats(self):
        scenes = split_script("A soldier enters. He looks toward the city! The sky darkens?")
        self.assertEqual(len(scenes), 3)
        self.assertEqual(scenes[0]["text"], "A soldier enters.")
        self.assertEqual(scenes[2]["text"], "The sky darkens?")

    def test_empty_script_fallback_is_predictable(self):
        scenes = split_script("A single scene")
        self.assertEqual(len(scenes), 1)
        self.assertEqual(scenes[0]["text"], "A single scene")

    def test_blender_scene_is_procedural_and_offline(self):
        self.assertIn("primitive_uv_sphere_add", BLENDER_SOURCE)
        self.assertIn("primitive_cylinder_add", BLENDER_SOURCE)
        self.assertIn("keyframe_insert", BLENDER_SOURCE)
        self.assertNotIn("requests.get", BLENDER_SOURCE)
        self.assertNotIn("urllib.request", BLENDER_SOURCE)


if __name__ == "__main__":
    unittest.main()

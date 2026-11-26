import json
import tempfile
import unittest
from pathlib import Path

from asset_library import (
    open_library,
    register_scene_asset,
    save_manifest,
    scene_signature,
    valid_scene_asset,
    candidate_asset_path,
    register_scene_candidates,
    select_scene_candidate,
    load_selection_file,
)


class AssetLibraryTests(unittest.TestCase):
    def test_project_library_is_stable_for_same_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            first, manifest1 = open_library(tmp, "myscript.txt", "same script")
            second, manifest2 = open_library(tmp, "myscript.txt", "same script")
            self.assertEqual(first, second)
            self.assertEqual(manifest1["project"], manifest2["project"])

    def test_scene_assets_resume_and_signature_invalidates_changed_scene(self):
        scene = {"text": "A historical scene", "queries": ["archive photo"]}
        with tempfile.TemporaryDirectory() as tmp:
            folder, manifest = open_library(tmp, "story.txt", "full script")
            path = folder / "scene_001.jpg"
            path.write_bytes(b"image-placeholder-for-path-existence")
            register_scene_asset(folder, manifest, 0, scene, "CC0 | source")
            self.assertIsNotNone(valid_scene_asset(folder, manifest, 0, scene))
            changed = dict(scene, text="A different scene")
            self.assertIsNone(valid_scene_asset(folder, manifest, 0, changed))
            saved = json.loads((folder / "asset_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["scenes"]["1"]["credit_and_source"], "CC0 | source")


    def test_candidate_selection_preserves_each_candidate_licence_and_source(self):
        scene = {"text": "A historical scene", "queries": ["archive photo"]}
        with tempfile.TemporaryDirectory() as tmp:
            folder, manifest = open_library(tmp, "story.txt", "full script")
            candidates = []
            for candidate_id, credit in (("c01", "Wikimedia Commons | licence: CC BY 4.0 | original source: https://one.example"),
                                          ("c02", "Openverse | licence: CC0 1.0 | original source: https://two.example")):
                path = candidate_asset_path(folder, 0, candidate_id)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"image-placeholder")
                candidates.append({"id": candidate_id, "file": path.relative_to(folder).as_posix(), "credit_and_source": credit})
            register_scene_candidates(folder, manifest, 0, scene, candidates)
            selected_path, record = select_scene_candidate(folder, manifest, 0, "c02")
            self.assertEqual(selected_path, folder / candidates[1]["file"])
            self.assertEqual(record["selected_candidate"], "c02")
            self.assertEqual(record["selection"], "manual")
            self.assertIn("CC0 1.0", record["credit_and_source"])
            saved = json.loads((folder / "asset_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(len(saved["scenes"]["1"]["candidates"]), 2)
            self.assertIn("CC BY 4.0", saved["scenes"]["1"]["candidates"][0]["credit_and_source"])

    def test_valid_scene_asset_uses_selected_candidate_and_selection_file(self):
        scene = {"text": "A historical scene", "queries": ["archive photo"]}
        with tempfile.TemporaryDirectory() as tmp:
            folder, manifest = open_library(tmp, "story.txt", "full script")
            path = candidate_asset_path(folder, 0, "c01")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"image-placeholder")
            register_scene_candidates(folder, manifest, 0, scene, [{"id": "c01", "file": path.relative_to(folder).as_posix(), "credit_and_source": "CC0 | archive"}])
            self.assertEqual(valid_scene_asset(folder, manifest, 0, scene)[0], path)
            (folder / "asset_selections.json").write_text('{"1": "c01"}', encoding="utf-8")
            self.assertEqual(load_selection_file(folder), {"1": "c01"})

if __name__ == "__main__":
    unittest.main()

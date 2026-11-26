import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import random  # noqa: E402
from pipeline import audio, audio_sync, director, story, variety  # noqa: E402

SCENES = [{"text": "Arjun walks into the dark forest at dusk in Kerala."},
          {"text": "He notices smoke rising above the trees, and fear grips him."},
          {"text": "In 1947 the village counted 12,500 people. By 2024 it had 48,000."},
          {"text": '"We carried the river in our hands," the elder said.'}]


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.scenes, self.bible = story.analyze(SCENES)

    def test_story_continuity(self):
        self.assertEqual(self.scenes[0]["subject"], "Arjun")
        self.assertEqual(self.scenes[1]["characters"][0], "Arjun")  # pronoun carry-over
        self.assertEqual(self.scenes[1]["location"], "forest")      # location inherited
        self.assertIn("smoke", self.scenes[1]["fx"])
        self.assertIn(self.scenes[1]["emotion"], ("fear", "curiosity"))

    def test_segments_archetypes_never_repeat(self):
        segs = director.segment(self.scenes)
        self.assertGreater(len(segs), len(self.scenes) - 1)
        arch = variety.assign_archetypes([x["text"] for x in segs], random.Random(1))
        self.assertTrue(all(a != b for a, b in zip(arch, arch[1:])))
        self.assertTrue(set(arch) <= set(variety.ARCHETYPES))
        shots = director.build_shots(segs, self.bible, "T", archetypes=arch)
        self.assertEqual(shots[0]["layout"], "title")
        self.assertEqual(shots[1]["lower_third"]["name"], "Arjun")
        out = director.retime(shots, {1: 5.0}, 24)
        self.assertEqual(sum(s["frames"] for s in out if s["scene_index"] == 1), 120)
        self.assertEqual(out[-1]["frame_start"] + out[-1]["frames"], sum(s["frames"] for s in out))

    def test_every_archetype_has_data(self):
        txt = {"animated_chart": "Sales grew from 10 to 20 to 45 million", "metric_counter": "It reached 85 percent",
               "historical_timeline": "In 1947 it began", "split_comparison": "Rome had 40 soldiers while Carthage had 90",
               "kinetic_quote": '"We carried the river in our hands," she said', "document_zoom": "The report says taxes rose",
               "concept_flow": "Drought hit crops, then prices rose and people left", "ken_burns_visual": "He looked at the sea"}
        for a, t in txt.items():
            sc, bb = story.analyze([{"text": t}])
            sh = director.build_shots(sc, bb, "T", archetypes=[a])[1]
            self.assertEqual(sh["archetype"], a)
            self.assertTrue({"chart", "stat", "years", "left", "quote", "doc", "nodes"} & set(sh) or a == "ken_burns_visual")

    def test_theme_history_never_repeats_consecutively(self):
        with tempfile.TemporaryDirectory() as td:
            h = Path(td) / "history.json"
            prev = None
            for k in range(12):
                th = variety.new_theme(h)
                if prev:
                    for key in ("palette", "fonts", "texture", "transition"):
                        self.assertNotEqual(th[key], prev[key])
                shots = director.build_shots(director.segment(self.scenes), self.bible, "T")
                variety.record_run(h, th, [dict(s, duration=3) for s in shots])
                prev = th
            self.assertEqual(len(variety.load_history(h)), 12)

    def test_word_sync_alignment(self):
        words = [(w, i * .5, i * .5 + .4) for i, w in enumerate("one two three four five six".split())]
        d = audio_sync.align(["one two three", "four five six"], words, 3.5)
        self.assertAlmostEqual(d[0], 1.42, places=1)
        self.assertAlmostEqual(sum(d), 3.5, places=1)

    def test_mix_filter_and_srt(self):
        f = audio.build_mix_filter([0, 1500], .35, 10)
        self.assertIn("sidechaincompress", f)
        self.assertIn("adelay=1500|1500", f)
        self.assertNotIn("sidechaincompress", audio.build_mix_filter([], .35, 10))
        self.assertEqual(audio._ts(3723.5), "01:02:03,500")

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg missing")
    def test_end_to_end_preview(self):
        from pipeline.orchestrator import run
        with tempfile.TemporaryDirectory() as td:
            sp = Path(td) / "s.txt"
            sp.write_text("\n".join(s["text"] for s in SCENES), encoding="utf-8")
            out = run(str(sp), str(Path(td) / "o.mp4"), resolution="preview", tts=False, workdir=str(Path(td) / "w"), seed=5, log=lambda *_: None)
            self.assertGreater(out.stat().st_size, 10_000)
            self.assertGreater(audio.probe_duration(out) or 0, 8)


if __name__ == "__main__":
    unittest.main()

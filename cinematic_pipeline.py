#!/usr/bin/env python3
"""Story-driven documentary pipeline CLI.  python cinematic_pipeline.py script.txt out.mp4 [--resolution 720p]"""
import argparse
import sys

from pipeline.orchestrator import RES, run


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("script"); ap.add_argument("output")
    ap.add_argument("--plan"); ap.add_argument("--resolution", choices=list(RES), default="720p")
    ap.add_argument("--max-scenes", type=int); ap.add_argument("--silent", action="store_true")
    ap.add_argument("--no-tts", action="store_true"); ap.add_argument("--voice", default="en-US-AndrewMultilingualNeural")
    ap.add_argument("--rate", default="+0%"); ap.add_argument("--workdir"); ap.add_argument("--nomusic", action="store_true")
    ap.add_argument("--musicvol", type=float, default=.35); ap.add_argument("--media", default="media")
    ap.add_argument("--seed", type=int, help="Fix theme_seed (default: random per run)")
    ap.add_argument("--whisper-model", default="base"); ap.add_argument("--history", help="history.json path")
    a = ap.parse_args(argv)
    try:
        run(a.script, a.output, plan_path=a.plan, resolution=a.resolution, max_scenes=a.max_scenes, silent=a.silent,
            tts=not a.no_tts, voice=a.voice, rate=a.rate, workdir=a.workdir, nomusic=a.nomusic, musicvol=a.musicvol, media=a.media,
            seed=a.seed, whisper_model=a.whisper_model, history=a.history)
    except (RuntimeError, ValueError, FileNotFoundError) as exc:
        print(f"[cinematic] ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

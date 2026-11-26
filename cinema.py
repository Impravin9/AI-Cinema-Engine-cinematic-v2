#!/usr/bin/env python3
"""Unified command-line entry point for the existing AI-Cinema-Engine.

Examples:
  python cinema.py myscript.txt output.mp4 --style lego
  python cinema.py myscript.txt output.mp4 --style realistic --plan plan.json
  python cinema.py myscript.txt --style realistic --prompt-only

This first integration layer deliberately delegates to the existing renderers.
It does not replace, import-patch, or rewrite their rendering internals.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from core.contracts import PlanValidationError, inspect_plan
from core.runner import EngineRunError, project_root, run_engine


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cinema.py",
        description="AI Cinema Engine — one director workflow, separate LEGO and realistic renderers.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("script", help="Input story/script text file.")
    parser.add_argument("out", nargs="?", default="output.mp4", help="Output MP4 path.")
    parser.add_argument("--cinematic-res", choices=("preview", "540p", "720p", "1080p"), default="720p",
                        help="Resolution for --style cinematic (documentary pipeline).")
    parser.add_argument("--style", choices=("lego", "realistic", "animation", "cinematic"), default="animation",
                        help="Rendering backend to use.")
    parser.add_argument("--plan", help="Reuse an existing JSON storyboard plan.")
    parser.add_argument("--provider", choices=("auto", "anthropic", "gemini", "groq", "openrouter", "ollama"),
                        default="auto", help="LLM provider used by the existing director.")
    parser.add_argument("--model", help="Optional LLM model override.")
    parser.add_argument("--save-plan", help="Where the selected renderer saves its generated plan.")
    parser.add_argument("--prompt-only", action="store_true",
                        help="Generate a prompt file for external LLM planning; do not render.")
    parser.add_argument("--fast", action="store_true", help="Use the LEGO renderer's faster quality setting.")
    parser.add_argument("--silent", action="store_true", help="Disable narration in either rendering mode.")

    # LEGO voice options
    parser.add_argument("--tts", choices=("edge",), help="Enable Edge TTS for LEGO narration.")
    parser.add_argument("--voice-name", default="en-US-GuyNeural", help="Edge TTS voice for LEGO mode.")
    parser.add_argument("--voice-file", help="Existing narration audio file for LEGO mode.")

    # Fully local procedural animation options
    parser.add_argument("--blender", help="Path to Blender executable (or set BLENDER_EXE).")
    parser.add_argument("--animation-fps", type=int, default=15, help="Animation frame rate.")
    parser.add_argument("--animation-seconds", type=float, default=6.0, help="Seconds per generated scene.")
    parser.add_argument("--max-scenes", type=int, help="Render only the first N scenes (useful for short tests).")

    # Realistic documentary options
    parser.add_argument("--content-style", choices=("history", "mythology", "news", "science", "animals", "story"),
                        help="Subject category for realistic mode (not the renderer selector).")
    parser.add_argument("--source", choices=("auto", "photo", "gen"), default="auto",
                        help="Compatibility setting; realistic still images come only from free, licence-filtered sources.")
    parser.add_argument("--media", default="media", help="Folder containing numbered local scene images.")
    parser.add_argument("--video-dir", default="media/videos", help="Folder containing your own licensed moving clips (scene_001.mp4, etc.).")
    parser.add_argument("--music", default="music", help="Folder containing royalty-free music tracks.")
    parser.add_argument("--cache", default="cache", help="Visual/audio cache directory.")
    parser.add_argument("--asset-library", default="assets", help="Persistent per-script image library directory.")
    parser.add_argument("--candidates-per-scene", type=int, default=3,
                        help="Licensed visual candidates to collect per scene (1-8).")
    parser.add_argument("--prepare-assets-only", action="store_true", help="Prepare all scene images and a contact sheet, then stop before rendering.")
    parser.add_argument("--offline", action="store_true", help="Render only from the prepared local asset library; never contact image websites.")
    parser.add_argument("--tts-voice", default="en-US-AndrewMultilingualNeural",
                        help="Narration voice in realistic mode.")
    parser.add_argument("--rate", default="+0%", help="Narration speed in realistic mode.")
    parser.add_argument("--preview", action="store_true", help="Render realistic mode at 640x360 / 12 fps.")
    parser.add_argument("--resolution", choices=("720p", "1080p"), default="1080p", help="Realistic output resolution.")
    parser.add_argument("--encoder", choices=("auto", "libx264", "h264_qsv"), default="auto", help="Intel Quick Sync when available; otherwise CPU encoding.")
    parser.add_argument("--allow-cards", action="store_true", help="Permit text-card fallback if all visual sources fail.")
    parser.add_argument("--endcard", action="store_true", help="Add an end card in realistic mode.")
    parser.add_argument("--nomusic", action="store_true", help="Disable the generated music bed.")
    parser.add_argument("--musicvol", type=float, default=0.55, help="Music bed volume.")
    return parser


def require_file(path: str, label: str) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_file():
        raise ValueError(f"{label} does not exist or is not a file: {candidate}")
    return candidate.resolve()


def build_renderer_args(args: argparse.Namespace) -> tuple[str, list[str]]:
    script = str(require_file(args.script, "Script"))
    output = Path(args.out).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    if args.style == "lego":
        renderer = "lego_boost.py"
        command = [script, str(output)]
        if args.plan:
            require_file(args.plan, "Plan")
            command += ["--plan", str(Path(args.plan).expanduser().resolve())]
        command += ["--provider", args.provider]
        if args.model:
            command += ["--model", args.model]
        if args.save_plan:
            command += ["--save-plan", args.save_plan]
        if args.prompt_only:
            command.append("--prompt-only")
        if args.fast:
            command.append("--fast")
        if args.tts:
            command += ["--tts", args.tts]
        if args.voice_name:
            command += ["--voice-name", args.voice_name]
        if args.silent:
            command.append("--silent")
        if args.voice_file:
            require_file(args.voice_file, "Voice file")
            command += ["--voice", str(Path(args.voice_file).expanduser().resolve())]
        return renderer, command

    if args.style == "cinematic":
        renderer = "cinematic_pipeline.py"
        command = [script, str(output), "--resolution", "preview" if args.preview else args.cinematic_res]
        if args.plan:
            require_file(args.plan, "Plan")
            command += ["--plan", str(Path(args.plan).expanduser().resolve())]
        if args.max_scenes is not None:
            command += ["--max-scenes", str(args.max_scenes)]
        if args.silent:
            command.append("--silent")
        if args.nomusic:
            command.append("--nomusic")
        return renderer, command

    if args.style == "animation":
        renderer = "animation_renderer.py"
        command = [script, str(output)]
        if args.plan:
            require_file(args.plan, "Plan")
            command += ["--plan", str(Path(args.plan).expanduser().resolve())]
        if args.blender:
            command += ["--blender", args.blender]
        command += ["--fps", str(args.animation_fps), "--seconds", str(args.animation_seconds)]
        if args.max_scenes is not None:
            command += ["--max-scenes", str(args.max_scenes)]
        if args.preview:
            command.append("--preview")
        if args.silent:
            command.append("--silent")
        return renderer, command

    renderer = "lego_modern.py"
    if shutil.which("ffmpeg") is None and not args.prompt_only and not args.prepare_assets_only:
        raise ValueError("FFmpeg was not found in PATH. Install it and reopen PowerShell: winget install Gyan.FFmpeg")
    command = [script, str(output)]
    if args.plan:
        require_file(args.plan, "Plan")
        plan_path = Path(args.plan).expanduser().resolve()
        diagnostics = inspect_plan(plan_path)
        print(
            f"[cinema] Plan detected: {diagnostics['schema']} schema, "
            f"{diagnostics['scene_count']} scenes ({diagnostics['title']}).",
            flush=True,
        )
        # lego_modern.adapt() explicitly supports the existing LEGO plan.json schema.
        command += ["--plan", str(plan_path)]
    command += ["--provider", args.provider]
    if args.model:
        command += ["--model", args.model]
    if args.save_plan:
        command += ["--save-plan", args.save_plan]
    if args.prompt_only:
        command.append("--prompt-only")
    command += ["--source", args.source, "--media", args.media, "--video-dir", args.video_dir, "--music", args.music, "--cache", args.cache, "--asset-library", args.asset_library, "--candidates-per-scene", str(args.candidates_per_scene)]
    if args.prepare_assets_only:
        command.append("--prepare-assets-only")
    if args.offline:
        command.append("--offline")
    command += ["--voice", args.tts_voice, "--rate", args.rate, "--musicvol", str(args.musicvol)]
    if args.content_style:
        command += ["--style", args.content_style]
    if args.preview:
        command.append("--preview")
    else:
        command += ["--resolution", args.resolution]
    command += ["--encoder", args.encoder]
    if args.allow_cards:
        command.append("--allow-cards")
    if args.silent:
        command.append("--silent")
    if args.endcard:
        command.append("--endcard")
    if args.nomusic:
        command.append("--nomusic")
    return renderer, command


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        renderer, renderer_args = build_renderer_args(args)
        print(f"[cinema] Backend: {args.style}", flush=True)
        return run_engine(renderer, renderer_args)
    except (ValueError, PlanValidationError, EngineRunError) as exc:
        print(f"[cinema] ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
